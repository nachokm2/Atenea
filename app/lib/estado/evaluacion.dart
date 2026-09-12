/// Estado del Desafío del módulo: pantalla de entrada y desafío (P11) y
/// resultado con revisión (P12).
///
/// Durante el desafío la retroalimentación es **mínima** (correcto o no, sin
/// explicación): la explicación se difiere a P12 para no convertir el desafío
/// en una lección.
library;

import 'package:flutter/foundation.dart';

import '../data/errores.dart';
import '../datos/repositorios.dart';

/// Fase del Desafío del módulo.
enum FaseEvaluacion {
  /// Nada abierto todavía.
  inactiva,

  /// Mostrando las reglas y la recompensa (P11 entrada).
  entrada,

  /// Respondiendo las preguntas del banco.
  enCurso,

  /// Enviando el intento.
  enviando,

  /// Resultado disponible (P12).
  resultado,
}

/// Desafío del módulo: información, intento, envío y revisión.
class ControladorEvaluacion extends ChangeNotifier {
  ControladorEvaluacion(this._repos);

  final Repositorios _repos;

  InfoEvaluacion? _info;
  IntentoEvaluacion? _intento;
  RevisionEvaluacion? _revision;
  ReciboRecompensas? _recibo;

  FaseEvaluacion _fase = FaseEvaluacion.inactiva;
  int _indice = 0;
  Object? _respuesta;
  bool? _ultimoAcierto;
  bool _registrando = false;
  bool _cargando = false;
  ErrorAtenea? _error;

  final Map<String, Object?> _respuestas = <String, Object?>{};
  final Map<String, String> _clavesRespuesta = <String, String>{};
  String? _claveEmpezar;
  String? _claveEnviar;
  DateTime? _iniciadaPregunta;

  // -------------------------------------------------------------------------
  // Lecturas
  // -------------------------------------------------------------------------

  /// Reglas, intentos, enfriamiento y recompensa anunciada.
  InfoEvaluacion? get info => _info;

  /// Intento abierto con sus preguntas.
  IntentoEvaluacion? get intento => _intento;

  /// Revisión pregunta a pregunta, para "Revisar respuestas" en P12.
  RevisionEvaluacion? get revision => _revision;

  /// Recibo del envío; su `resultadoEvaluacion` alimenta P12.
  ReciboRecompensas? get recibo => _recibo;

  /// Resultado del intento: puntaje, desglose por tema y temas débiles.
  ResultadoEvaluacionModulo? get resultado => _recibo?.resultadoEvaluacion;

  /// Fase vigente.
  FaseEvaluacion get fase => _fase;

  /// Índice de la pregunta visible.
  int get indice => _indice;

  /// Pregunta visible.
  Pregunta? get preguntaActual {
    final List<Pregunta> preguntas = _intento?.preguntas ?? const <Pregunta>[];
    return _indice >= 0 && _indice < preguntas.length ? preguntas[_indice] : null;
  }

  /// Total de preguntas del intento.
  int get total => _intento?.totalPreguntas ?? 0;

  /// Avance del desafío entre 0 y 1.
  double get fraccion =>
      total <= 0 ? 0 : ((_indice + 1) / total).clamp(0, 1).toDouble();

  /// Respuesta marcada ahora mismo.
  Object? get respuesta => _respuesta;

  /// Retroalimentación mínima de la última respuesta registrada.
  bool? get ultimoAcierto => _ultimoAcierto;

  /// Lo que respondió el usuario, por identificador de pregunta. P12 lo usa
  /// para mostrar la respuesta elegida junto a la correcta.
  Map<String, Object?> get respuestasDadas =>
      Map<String, Object?>.unmodifiable(_respuestas);

  /// ¿Se está registrando una respuesta?
  bool get registrando => _registrando;

  /// Carga en curso.
  bool get cargando => _cargando;

  /// Último error, ya en español.
  ErrorAtenea? get error => _error;

  /// ¿Se puede pulsar "Comprobar"?
  bool get puedeResponder => preguntaActual != null && !_registrando && _hayRespuesta;

  /// ¿Es la última pregunta?
  bool get esUltima => total > 0 && _indice >= total - 1;

  /// ¿Hay un intento a medias? El enrutador lo consulta al salir con la X.
  bool get enProgreso => _fase == FaseEvaluacion.enCurso;

  /// ¿El desafío se puede empezar ahora?
  bool get puedeEmpezar => _info?.puedeEmpezar ?? false;

  // -------------------------------------------------------------------------
  // Flujo
  // -------------------------------------------------------------------------

  /// Abre la pantalla de entrada de P11 con las reglas del módulo.
  Future<void> abrir(String moduloId) async {
    if (_cargando) return;
    _reiniciar();
    _cargando = true;
    _fase = FaseEvaluacion.entrada;
    notifyListeners();
    try {
      _info = await _repos.evaluacion.info(moduloId);
      _error = null;
    } catch (e) {
      _error = _comoError(e);
    } finally {
      _cargando = false;
      notifyListeners();
    }
  }

  /// Comienza el intento y descarga el banco de preguntas.
  Future<bool> comenzar() async {
    final String? evaluacionId = _info?.evaluacion.id;
    if (evaluacionId == null || evaluacionId.isEmpty || _cargando) return false;
    _cargando = true;
    _error = null;
    notifyListeners();
    _claveEmpezar ??= claveDeterminista(
      'assessment-start',
      evaluacionId,
      (_info?.intentosUsados ?? 0) + 1,
    );
    try {
      _intento = await _repos.evaluacion.empezar(
        evaluacionId,
        clave: _claveEmpezar,
      );
      _indice = 0;
      _respuesta = null;
      _ultimoAcierto = null;
      _iniciadaPregunta = DateTime.now();
      _fase = FaseEvaluacion.enCurso;
      return true;
    } catch (e) {
      _error = _comoError(e);
      return false;
    } finally {
      _cargando = false;
      notifyListeners();
    }
  }

  /// Guarda la respuesta marcada.
  void seleccionar(Object? valor) {
    if (_registrando) return;
    _respuesta = valor;
    notifyListeners();
  }

  /// Registra la respuesta en el servidor y avanza.
  ///
  /// Si es la última, deja el intento listo para [enviar].
  Future<void> responder() async {
    final IntentoEvaluacion? intento = _intento;
    final Pregunta? pregunta = preguntaActual;
    if (intento == null || pregunta == null || _registrando || !_hayRespuesta) {
      return;
    }
    _registrando = true;
    _error = null;
    notifyListeners();
    final String clave = _clavesRespuesta.putIfAbsent(
      pregunta.id,
      () => claveDeterminista('assessment-answer', '${intento.id}:${pregunta.id}'),
    );
    try {
      final RegistroRespuesta eco = await _repos.evaluacion.responder(
        intento.id,
        preguntaId: pregunta.id,
        respuesta: _respuesta ?? '',
        milisegundos: _milisegundosDePregunta(),
        clave: clave,
      );
      _respuestas[pregunta.id] = _respuesta;
      _ultimoAcierto = eco.esCorrecta;
      if (!esUltima) {
        _indice += 1;
        _respuesta = null;
        _iniciadaPregunta = DateTime.now();
      }
    } catch (e) {
      _error = _comoError(e);
    } finally {
      _registrando = false;
      notifyListeners();
    }
  }

  /// Envía el intento y trae el recibo con el resultado (P12).
  Future<void> enviar() async {
    final IntentoEvaluacion? intento = _intento;
    if (intento == null || _fase == FaseEvaluacion.enviando) return;
    _fase = FaseEvaluacion.enviando;
    _error = null;
    notifyListeners();
    _claveEnviar ??= claveDeterminista('assessment-submit', intento.id);
    try {
      _recibo = await _repos.evaluacion.enviar(intento.id, clave: _claveEnviar);
      _fase = FaseEvaluacion.resultado;
    } catch (e) {
      _error = _comoError(e);
      _fase = FaseEvaluacion.enCurso;
    } finally {
      notifyListeners();
    }
  }

  /// Carga la revisión pregunta a pregunta para P12.
  Future<void> cargarRevision() async {
    final String? intentoId = _intento?.id;
    if (intentoId == null) return;
    try {
      _revision = await _repos.evaluacion.revision(intentoId);
      _error = null;
    } catch (e) {
      _error = _comoError(e);
    }
    notifyListeners();
  }

  /// Prepara un nuevo intento con preguntas distintas.
  Future<bool> reintentar() async {
    final String? moduloId = _info?.moduloId ?? _intento?.moduloId;
    _intento = null;
    _recibo = null;
    _revision = null;
    _respuestas.clear();
    _clavesRespuesta.clear();
    _claveEmpezar = null;
    _claveEnviar = null;
    _indice = 0;
    _respuesta = null;
    _ultimoAcierto = null;
    _fase = FaseEvaluacion.entrada;
    notifyListeners();
    if (moduloId != null) await abrir(moduloId);
    return comenzar();
  }

  /// Sale del desafío perdiendo el intento (no el progreso del módulo).
  void abandonar() {
    _intento = null;
    _respuestas.clear();
    _clavesRespuesta.clear();
    _claveEmpezar = null;
    _indice = 0;
    _respuesta = null;
    _ultimoAcierto = null;
    _fase = _info == null ? FaseEvaluacion.inactiva : FaseEvaluacion.entrada;
    notifyListeners();
  }

  /// Borra el error visible.
  void limpiarError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  /// Deja el controlador listo para otro módulo.
  void cerrar() {
    _reiniciar();
    notifyListeners();
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

  int _milisegundosDePregunta() {
    final DateTime? desde = _iniciadaPregunta;
    if (desde == null) return 0;
    final int ms = DateTime.now().difference(desde).inMilliseconds;
    return ms < 0 ? 0 : ms;
  }

  void _reiniciar() {
    _info = null;
    _intento = null;
    _revision = null;
    _recibo = null;
    _fase = FaseEvaluacion.inactiva;
    _indice = 0;
    _respuesta = null;
    _ultimoAcierto = null;
    _registrando = false;
    _error = null;
    _respuestas.clear();
    _clavesRespuesta.clear();
    _claveEmpezar = null;
    _claveEnviar = null;
    _iniciadaPregunta = null;
  }
}

/// Traduce cualquier fallo a un [ErrorAtenea] con mensaje en español.
ErrorAtenea _comoError(Object error) => error is ErrorAtenea
    ? error
    : const ErrorAtenea(
        codigo: 'inesperado',
        mensaje: 'Ocurrió algo inesperado. Inténtalo de nuevo.',
      );
