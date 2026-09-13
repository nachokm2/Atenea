/// Estado de la Lección (P08), la pregunta con retroalimentación (P09) y el
/// cierre con recompensas (P10).
///
/// El XP que se muestra **siempre** viene del servidor: de `xp_awarded` en
/// cada respuesta y del [ReciboRecompensas] al completar. Aquí no se calcula
/// nada.
library;

import 'dart:async';

import 'package:flutter/widgets.dart';

import '../data/errores.dart';
import '../datos/repositorios.dart';

/// Un paso de la lección: o un bloque de contenido, o una pregunta.
class PasoLeccion {
  const PasoLeccion({required this.indice, this.bloque, this.pregunta});

  /// Posición del paso dentro de la lección, empezando en 0.
  final int indice;

  /// Bloque de explicación, ejemplo, código, diagrama o cierre.
  final BloqueLeccion? bloque;

  /// Pregunta que hay que responder en este paso.
  final Pregunta? pregunta;

  /// ¿Este paso pide una respuesta?
  bool get esPregunta => pregunta != null;

  /// ¿Este paso es el cierre de la lección?
  bool get esCierre => bloque?.tipo == TipoBloque.resumen;
}

/// Fase de la pregunta que se está viendo en P09.
enum FasePregunta {
  /// Todavía no se ha seleccionado nada.
  respondiendo,

  /// Se pulsó "Comprobar" y el Reino está corrigiendo.
  comprobando,

  /// Ya hay veredicto: el panel de retroalimentación está arriba.
  retroalimentacion,
}

/// Lección abierta: pasos, respuestas, latido de tiempo y recibo final.
class ControladorLeccion extends ChangeNotifier with WidgetsBindingObserver {
  ControladorLeccion(this._repos);

  /// Cada cuánto se informa el tiempo efectivo (§7.6 `heartbeat`).
  /// No es una duración de animación: es política de medición.
  static const Duration cadenciaLatido = Duration(seconds: 30);

  final Repositorios _repos;

  Leccion? _leccion;
  Actividad? _actividad;
  List<PasoLeccion> _pasos = const <PasoLeccion>[];
  int _indice = 0;

  Object? _respuesta;
  FasePregunta _fasePregunta = FasePregunta.respondiendo;
  ResultadoRespuesta? _resultado;
  final Map<String, ResultadoRespuesta> _resueltas =
      <String, ResultadoRespuesta>{};
  final List<Pregunta> _porReintentar = <Pregunta>[];
  final Set<String> _yaReintentadas = <String>{};

  int _xpDeRespuestas = 0;
  ReciboRecompensas? _recibo;

  bool _cargando = false;
  bool _cerrando = false;
  ErrorAtenea? _error;

  Timer? _latido;
  DateTime? _ultimoLatido;
  int _segundosAcumulados = 0;
  bool _enPrimerPlano = true;

  String? _claveCompletar;
  final Map<String, String> _clavesRespuesta = <String, String>{};

  /// Cuántas veces se ha enviado ya cada pregunta de esta actividad.
  final Map<String, int> _intentosPorPregunta = <String, int>{};

  // -------------------------------------------------------------------------
  // Lecturas
  // -------------------------------------------------------------------------

  /// Lección abierta con sus bloques.
  Leccion? get leccion => _leccion;

  /// Actividad en curso (el intento abierto en el servidor).
  Actividad? get actividad => _actividad;

  /// Pasos ya ordenados: contenido y preguntas intercaladas.
  List<PasoLeccion> get pasos => List<PasoLeccion>.unmodifiable(_pasos);

  /// Índice del paso visible.
  int get indice => _indice;

  /// Paso visible, o `null` si todavía no hay lección.
  PasoLeccion? get pasoActual =>
      _indice >= 0 && _indice < _pasos.length ? _pasos[_indice] : null;

  /// Pregunta del paso visible, si la hay.
  Pregunta? get preguntaActual => pasoActual?.pregunta;

  /// Total de pasos, para la barra segmentada de P08.
  int get totalPasos => _pasos.length;

  /// Avance de la lección entre 0 y 1.
  double get fraccion =>
      _pasos.isEmpty ? 0 : ((_indice + 1) / _pasos.length).clamp(0, 1).toDouble();

  /// Respuesta que el usuario tiene seleccionada ahora mismo.
  Object? get respuesta => _respuesta;

  /// Fase de la pregunta visible.
  FasePregunta get fasePregunta => _fasePregunta;

  /// Veredicto de la última respuesta comprobada.
  ResultadoRespuesta? get resultado => _resultado;

  /// XP de preguntas acumulado en esta lección, sumando lo que otorgó el
  /// servidor en cada respuesta.
  int get xpDeRespuestas => _xpDeRespuestas;

  /// Recibo de recompensas del cierre (P10). Alimenta la cola de
  /// celebraciones.
  ReciboRecompensas? get recibo => _recibo;

  /// Primera carga en curso.
  bool get cargando => _cargando;

  /// Cierre en curso (`complete`).
  bool get cerrando => _cerrando;

  /// Último error, ya en español.
  ErrorAtenea? get error => _error;

  /// ¿Hay una lección abierta a medias? Lo consulta el enrutador antes de
  /// dejar salir del flujo inmersivo.
  bool get enProgreso => _actividad != null && _recibo == null;

  /// ¿Se puede pulsar "Comprobar"?
  bool get puedeComprobar =>
      preguntaActual != null &&
      _fasePregunta == FasePregunta.respondiendo &&
      _hayRespuesta;

  /// ¿Se puede pulsar "Continuar"?
  bool get puedeContinuar {
    final PasoLeccion? paso = pasoActual;
    if (paso == null) return false;
    if (!paso.esPregunta) return true;
    return _fasePregunta == FasePregunta.retroalimentacion;
  }

  /// ¿Este es el último paso?
  bool get esUltimoPaso => _indice >= _pasos.length - 1;

  /// La lección es un repaso: el XP de lección no se vuelve a otorgar.
  bool get esRepaso => _leccion?.esRepaso ?? false;

  /// Segundos efectivos medidos en esta sesión de estudio.
  int get segundosActivos => _segundosAcumulados;

  // -------------------------------------------------------------------------
  // Ciclo de la lección
  // -------------------------------------------------------------------------

  /// Abre la lección y su actividad. [clave] permite reintentar la apertura
  /// sin abrir dos intentos.
  Future<void> abrir(String leccionId) async {
    if (_cargando) return;
    _reiniciar();
    _cargando = true;
    notifyListeners();
    try {
      _leccion = await _repos.leccion.leccion(leccionId);
      _actividad = await _repos.leccion.empezar(
        leccionId,
        clave: claveDeterminista('lesson-start', leccionId),
      );
      _pasos = _armarPasos(_leccion!, _actividad!);
      _error = null;
      _arrancarLatido();
    } catch (e) {
      _error = _comoError(e);
    } finally {
      _cargando = false;
      notifyListeners();
    }
  }

  /// Abre un repaso de un tema (sin lección de origen).
  Future<void> abrirRepaso(String temaId) async {
    if (_cargando) return;
    _reiniciar();
    _cargando = true;
    notifyListeners();
    try {
      _actividad = await _repos.leccion.empezarRepaso(
        temaId,
        clave: claveDeterminista('review-start', temaId),
      );
      _pasos = <PasoLeccion>[
        for (int i = 0; i < _actividad!.preguntas.length; i++)
          PasoLeccion(indice: i, pregunta: _actividad!.preguntas[i]),
      ];
      _error = null;
      _arrancarLatido();
    } catch (e) {
      _error = _comoError(e);
    } finally {
      _cargando = false;
      notifyListeners();
    }
  }

  /// Guarda la respuesta que el usuario tiene marcada.
  void seleccionar(Object? valor) {
    if (_fasePregunta != FasePregunta.respondiendo) return;
    _respuesta = valor;
    notifyListeners();
  }

  /// Envía la respuesta y trae la retroalimentación del Reino.
  Future<void> comprobar() async {
    final Pregunta? pregunta = preguntaActual;
    final Actividad? actividad = _actividad;
    if (pregunta == null || actividad == null) return;
    if (_fasePregunta != FasePregunta.respondiendo || !_hayRespuesta) return;

    _fasePregunta = FasePregunta.comprobando;
    _error = null;
    notifyListeners();

    // La clave lleva el número de intento. Sin él, responder por segunda vez a
    // la misma pregunta reenvía la misma clave y el Reino devuelve el veredicto
    // del primer intento sin corregir nada: la revancha quedaría anulada y el
    // acierto no contaría para el dominio.
    final int intento = (_intentosPorPregunta[pregunta.id] ?? 0) + 1;
    _intentosPorPregunta[pregunta.id] = intento;
    final String clave = _clavesRespuesta.putIfAbsent(
      '${pregunta.id}:$intento',
      () => claveDeterminista('answer', '${actividad.id}:${pregunta.id}', intento),
    );
    final int milisegundos = _milisegundosDesdeLatido();

    try {
      final ResultadoRespuesta veredicto = await _repos.leccion.responder(
        actividad.id,
        preguntaId: pregunta.id,
        tipo: pregunta.tipo,
        respuesta: _respuesta ?? '',
        milisegundos: milisegundos,
        clave: clave,
      );
      _resultado = veredicto;
      _resueltas[pregunta.id] = veredicto;
      _xpDeRespuestas += veredicto.xpOtorgado;
      _fasePregunta = FasePregunta.retroalimentacion;
      _encolarReintentoSiFalla(pregunta, veredicto);
    } catch (e) {
      _error = _comoError(e);
      _fasePregunta = FasePregunta.respondiendo;
    } finally {
      notifyListeners();
    }
  }

  /// Avanza al siguiente paso. Al terminar el último, encola las preguntas
  /// falladas una sola vez y, si ya no quedan, cierra la lección.
  Future<void> continuar() async {
    if (!puedeContinuar) return;
    if (_indice < _pasos.length - 1) {
      _indice += 1;
      _prepararPaso();
      notifyListeners();
      return;
    }
    if (_porReintentar.isNotEmpty) {
      final List<Pregunta> cola = List<Pregunta>.of(_porReintentar);
      _porReintentar.clear();
      final int base = _pasos.length;
      _pasos = <PasoLeccion>[
        ..._pasos,
        for (int i = 0; i < cola.length; i++)
          PasoLeccion(indice: base + i, pregunta: cola[i]),
      ];
      _indice += 1;
      _prepararPaso();
      notifyListeners();
      return;
    }
    await finalizar();
  }

  /// Vuelve un paso atrás sin perder lo respondido.
  void retroceder() {
    if (_indice == 0) return;
    _indice -= 1;
    _prepararPaso();
    notifyListeners();
  }

  /// Cierra la lección y trae el [ReciboRecompensas] de P10.
  Future<void> finalizar() async {
    final Actividad? actividad = _actividad;
    if (actividad == null || _cerrando || _recibo != null) return;
    _cerrando = true;
    _error = null;
    notifyListeners();
    _claveCompletar ??= claveDeterminista('lesson-complete', actividad.id);
    try {
      await _enviarLatido();
      _recibo = await _repos.leccion.completar(
        actividad.id,
        clave: _claveCompletar,
      );
      _detenerLatido();
    } catch (e) {
      _error = _comoError(e);
    } finally {
      _cerrando = false;
      notifyListeners();
    }
  }

  /// Abandona la lección conservando el paso (X con confirmación, §3.3).
  Future<void> abandonar() async {
    final Actividad? actividad = _actividad;
    _detenerLatido();
    if (actividad == null) {
      _reiniciar();
      notifyListeners();
      return;
    }
    try {
      await _enviarLatido();
      await _repos.leccion.abandonar(actividad.id);
    } catch (_) {
      // El avance ya quedó guardado con los latidos: si el cierre falla, no
      // se le dice nada al usuario.
    }
    _reiniciar();
    notifyListeners();
  }

  /// Pide otra explicación del tema ("No lo entiendo").
  Future<Explicacion?> reexplicar({String? enfoque}) async {
    final String? temaId = _leccion?.temaId ?? _actividad?.temaId;
    if (temaId == null) return null;
    try {
      return await _repos.leccion.reexplicar(temaId, enfoque: enfoque);
    } catch (e) {
      _error = _comoError(e);
      notifyListeners();
      return null;
    }
  }

  /// Reporta un bloque o una pregunta como incorrecta.
  Future<bool> reportar({
    required TipoContenido tipoContenido,
    required String contenidoId,
    required String motivo,
    String? comentario,
  }) async {
    try {
      await _repos.leccion.reportar(
        tipoContenido: tipoContenido,
        contenidoId: contenidoId,
        motivo: motivo,
        comentario: comentario,
      );
      return true;
    } catch (e) {
      _error = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  /// Borra el error para que la pantalla deje de mostrarlo.
  void limpiarError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  /// Deja la lección lista para abrir otra.
  void cerrar() {
    _detenerLatido();
    _reiniciar();
    notifyListeners();
  }

  // -------------------------------------------------------------------------
  // Latido de tiempo efectivo
  // -------------------------------------------------------------------------

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final bool activo = state == AppLifecycleState.resumed;
    if (activo == _enPrimerPlano) return;
    _enPrimerPlano = activo;
    if (activo) {
      _ultimoLatido = DateTime.now();
    } else {
      unawaited(_enviarLatido());
    }
  }

  void _arrancarLatido() {
    _detenerLatido();
    _ultimoLatido = DateTime.now();
    WidgetsBinding.instance.addObserver(this);
    _latido = Timer.periodic(
      cadenciaLatido,
      (Timer _) => unawaited(_enviarLatido()),
    );
  }

  void _detenerLatido() {
    _latido?.cancel();
    _latido = null;
    WidgetsBinding.instance.removeObserver(this);
  }

  Future<void> _enviarLatido() async {
    final Actividad? actividad = _actividad;
    final DateTime? desde = _ultimoLatido;
    if (actividad == null || desde == null || !_enPrimerPlano) return;
    final int segundos = DateTime.now().difference(desde).inSeconds;
    if (segundos <= 0) return;
    _ultimoLatido = DateTime.now();
    try {
      final LatidoActividad eco =
          await _repos.leccion.latido(actividad.id, segundos);
      _segundosAcumulados = eco.segundosActivos;
      notifyListeners();
    } catch (_) {
      // El tiempo se reintenta en el siguiente latido; jamás molestamos al
      // usuario con esto.
    }
  }

  int _milisegundosDesdeLatido() {
    final DateTime? desde = _ultimoLatido;
    if (desde == null) return 0;
    final int ms = DateTime.now().difference(desde).inMilliseconds;
    return ms < 0 ? 0 : ms;
  }

  // -------------------------------------------------------------------------
  // Interno
  // -------------------------------------------------------------------------

  bool get _hayRespuesta {
    final Object? r = _respuesta;
    if (r == null) return false;
    if (r is String) return r.trim().isNotEmpty;
    if (r is Iterable) return r.isNotEmpty;
    if (r is Map) return r.isNotEmpty;
    return true;
  }

  void _prepararPaso() {
    final Pregunta? pregunta = preguntaActual;
    if (pregunta == null) {
      _respuesta = null;
      _resultado = null;
      _fasePregunta = FasePregunta.respondiendo;
      return;
    }
    final ResultadoRespuesta? yaResuelta = _resueltas[pregunta.id];
    _resultado = yaResuelta;
    _respuesta = null;
    _fasePregunta = yaResuelta == null
        ? FasePregunta.respondiendo
        : FasePregunta.retroalimentacion;
  }

  void _encolarReintentoSiFalla(Pregunta pregunta, ResultadoRespuesta v) {
    final bool fallo = !v.esCorrecta && !v.esParcial && !v.estaPendiente;
    if (!fallo) return;
    if (_yaReintentadas.contains(pregunta.id)) return;
    _yaReintentadas.add(pregunta.id);
    _porReintentar.add(pregunta);
  }

  void _reiniciar() {
    _leccion = null;
    _actividad = null;
    _pasos = const <PasoLeccion>[];
    _indice = 0;
    _respuesta = null;
    _resultado = null;
    _fasePregunta = FasePregunta.respondiendo;
    _resueltas.clear();
    _porReintentar.clear();
    _yaReintentadas.clear();
    _clavesRespuesta.clear();
    _intentosPorPregunta.clear();
    _claveCompletar = null;
    _xpDeRespuestas = 0;
    _recibo = null;
    _error = null;
    _segundosAcumulados = 0;
    _ultimoLatido = null;
  }

  /// Intercala los bloques de la lección con las preguntas de la actividad.
  ///
  /// Un bloque de tipo pregunta toma la pregunta con su mismo identificador;
  /// las preguntas que la actividad trae y que ningún bloque reclama se
  /// añaden al final, antes del cierre.
  static List<PasoLeccion> _armarPasos(Leccion leccion, Actividad actividad) {
    final Map<String, Pregunta> porId = <String, Pregunta>{
      for (final Pregunta p in actividad.preguntas) p.id: p,
    };
    final Set<String> usadas = <String>{};
    final List<PasoLeccion> cuerpo = <PasoLeccion>[];
    final List<PasoLeccion> cierre = <PasoLeccion>[];

    for (final BloqueLeccion bloque in leccion.bloques) {
      final String? preguntaId = bloque.preguntaId;
      final Pregunta? pregunta =
          preguntaId == null ? null : porId[preguntaId] ?? bloque.pregunta;
      if (pregunta != null) {
        usadas.add(pregunta.id);
        cuerpo.add(PasoLeccion(indice: cuerpo.length, pregunta: pregunta));
        continue;
      }
      if (bloque.tipo == TipoBloque.preguntaIntercalada) continue;
      final PasoLeccion paso = PasoLeccion(indice: 0, bloque: bloque);
      if (bloque.tipo == TipoBloque.resumen) {
        cierre.add(paso);
      } else {
        cuerpo.add(paso);
      }
    }

    final List<PasoLeccion> sueltas = <PasoLeccion>[
      for (final Pregunta p in actividad.preguntas)
        if (!usadas.contains(p.id)) PasoLeccion(indice: 0, pregunta: p),
    ];

    final List<PasoLeccion> todo = <PasoLeccion>[
      ...cuerpo,
      ...sueltas,
      ...cierre,
    ];
    return <PasoLeccion>[
      for (int i = 0; i < todo.length; i++)
        PasoLeccion(
          indice: i,
          bloque: todo[i].bloque,
          pregunta: todo[i].pregunta,
        ),
    ];
  }

  @override
  void dispose() {
    _detenerLatido();
    super.dispose();
  }
}

/// Traduce cualquier fallo a un [ErrorAtenea] con mensaje en español.
ErrorAtenea _comoError(Object error) => error is ErrorAtenea
    ? error
    : const ErrorAtenea(
        codigo: 'inesperado',
        mensaje: 'Ocurrió algo inesperado. Inténtalo de nuevo.',
      );
