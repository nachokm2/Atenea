/// Estado de la Aventura: mis territorios (P22), la creación de una Ruta
/// (P05), el estado de generación (P06) y el mapa de la Ruta (P07).
///
/// Nada de lo que hay aquí calcula progreso, dominio ni recompensas: todo
/// llega resuelto desde el servidor.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../data/errores.dart';
import '../datos/repositorios.dart';

/// Ciclo de vida de un archivo que el usuario adjunta en P05.
enum EstadoSubida {
  /// En la lista pero todavía sin enviar.
  pendiente,

  /// Enviándose, con progreso.
  subiendo,

  /// El Reino ya lo recibió y lo está procesando.
  listo,

  /// Falló; se puede reintentar con la misma clave de idempotencia.
  fallida,
}

/// Un archivo adjunto de P05 con su progreso de subida.
class SubidaDocumento {
  SubidaDocumento({
    required this.id,
    required this.nombreArchivo,
    required this.bytes,
    required this.clave,
    this.titulo,
  });

  /// Identificador local, solo para la lista de la pantalla.
  final String id;

  /// Nombre original del archivo.
  final String nombreArchivo;

  /// Contenido; se conserva para poder reintentar sin volver a elegirlo.
  final List<int> bytes;

  /// Clave de idempotencia de esta subida. **Se reutiliza al reintentar.**
  final String clave;

  /// Título que verá el usuario; por defecto, el nombre del archivo.
  final String? titulo;

  /// Estado actual.
  EstadoSubida estado = EstadoSubida.pendiente;

  /// Bytes ya enviados.
  int enviados = 0;

  /// Documento devuelto por el Reino cuando termina.
  Documento? documento;

  /// Mensaje de fallo en español.
  String? error;

  /// Tamaño total en bytes.
  int get total => bytes.length;

  /// Avance de 0 a 1.
  double get fraccion =>
      total <= 0 ? 0 : (enviados / total).clamp(0, 1).toDouble();

  /// Tamaño legible ("2,1 MB").
  String get tamanoLegible {
    if (total < 1024) return '$total B';
    if (total < 1024 * 1024) {
      return '${(total / 1024).toStringAsFixed(0)} KB';
    }
    return '${(total / (1024 * 1024)).toStringAsFixed(1).replaceAll('.', ',')} MB';
  }

  /// ¿Se puede usar como fuente de la Ruta?
  bool get estaListo => estado == EstadoSubida.listo && documento != null;
}

/// Mis rutas, creación, generación y mapa.
class ControladorAventura extends ChangeNotifier {
  ControladorAventura(this._repos);

  /// Cadencia del sondeo de `/paths/{id}/generation` (§P06: cada 2–3 s).
  /// No es una duración de animación: es política de red.
  static const Duration intervaloSondeo = Duration(seconds: 3);

  /// A partir de aquí P06 avisa "está tardando más de lo normal" (§8.2).
  static const Duration esperaLarga = Duration(minutes: 10);

  /// Límites iniciales del material adjunto en P05.
  static const int maxArchivos = 10;

  /// 50 MB en total entre todos los archivos.
  static const int maxBytesTotales = 50 * 1024 * 1024;

  /// Formatos que el Reino sabe leer (OCR fuera del MVP).
  static const List<String> extensionesPermitidas = <String>[
    'pdf',
    'docx',
    'txt',
    'md',
  ];

  final Repositorios _repos;

  // --- Listas de P22 -------------------------------------------------------
  List<ResumenRuta> _mias = const <ResumenRuta>[];
  List<ResumenRuta> _delReino = const <ResumenRuta>[];
  List<Territorio> _territorios = const <Territorio>[];
  String? _cursorMias;
  bool _hayMasMias = false;
  bool _cargandoRutas = false;
  bool _cargandoMas = false;
  ErrorAtenea? _errorRutas;

  // --- Borrador de P05 -----------------------------------------------------
  String _objetivo = '';
  NivelDeclarado _nivel = NivelDeclarado.principiante;
  String? _pistaConocimiento;
  int _minutosAlDia = 10;
  final List<SubidaDocumento> _adjuntos = <SubidaDocumento>[];
  String _claveCrear = claveIdempotencia();
  bool _creando = false;
  ErrorAtenea? _errorCreacion;
  String? _avisoArchivo;

  // --- Generación de P06 ---------------------------------------------------
  EstadoGeneracion? _generacion;
  String? _rutaEnGeneracion;
  Timer? _sonda;
  DateTime? _inicioSondeo;
  ErrorAtenea? _errorGeneracion;

  // --- Detalle de P07 ------------------------------------------------------
  DetalleRuta? _ruta;
  bool _cargandoRuta = false;
  ErrorAtenea? _errorRuta;
  List<Documento> _fuentes = const <Documento>[];

  // -------------------------------------------------------------------------
  // Lecturas
  // -------------------------------------------------------------------------

  /// Mis rutas, en el orden que envía el Reino.
  ///
  /// Se llamaba «mis territorios» y no lo son: un conocimiento con dos rutas
  /// sale dos veces, y uno con dominio pero sin ruta no sale nunca. Los
  /// territorios son otra cosa y ahora están al lado, en [territorios].
  List<ResumenRuta> get mias => List<ResumenRuta>.unmodifiable(_mias);

  /// Rutas del Reino, curadas y pregeneradas.
  List<ResumenRuta> get delReino => List<ResumenRuta>.unmodifiable(_delReino);

  /// El mapa del Reino: los siete territorios con el estado de cada uno.
  ///
  /// Vacío mientras no lleguen, y vacío también si fallan: la sección
  /// simplemente no se pinta. Ver [cargarTerritorios].
  List<Territorio> get territorios => List<Territorio>.unmodifiable(_territorios);

  /// ¿Quedan más rutas propias por traer?
  bool get hayMasMias => _hayMasMias;

  /// Primera carga de las listas.
  bool get cargandoRutas => _cargandoRutas;

  /// Trayendo la siguiente página.
  bool get cargandoMas => _cargandoMas;

  /// Error de las listas.
  ErrorAtenea? get errorRutas => _errorRutas;

  /// ¿El usuario todavía no tiene ninguna ruta propia?
  bool get sinRutasPropias => _mias.isEmpty;

  /// Objetivo escrito en P05.
  String get objetivo => _objetivo;

  /// Nivel declarado en P05.
  NivelDeclarado get nivel => _nivel;

  /// Minutos al día que declara el usuario (informativo, no viaja a la API).
  int get minutosAlDia => _minutosAlDia;

  /// Archivos adjuntos con su progreso.
  List<SubidaDocumento> get adjuntos =>
      List<SubidaDocumento>.unmodifiable(_adjuntos);

  /// ¿Hay una creación de ruta en vuelo?
  bool get creando => _creando;

  /// Error de la creación.
  ErrorAtenea? get errorCreacion => _errorCreacion;

  /// Aviso del último archivo rechazado ("No admitimos ese formato…").
  String? get avisoArchivo => _avisoArchivo;

  /// Bytes ocupados por los adjuntos.
  int get bytesAdjuntos =>
      _adjuntos.fold<int>(0, (int suma, SubidaDocumento a) => suma + a.total);

  /// ¿Hay algún archivo todavía en vuelo?
  bool get subiendoArchivos =>
      _adjuntos.any((SubidaDocumento a) => a.estado == EstadoSubida.subiendo);

  /// El objetivo tiene sustancia suficiente para enviar.
  bool get objetivoValido => _objetivo.trim().length >= 8;

  /// ¿Se puede pulsar "Construir mi ruta"?
  bool get puedeCrear => objetivoValido && !_creando && !subiendoArchivos;

  /// Modo de fuente que se enviará: con material si hay algún documento listo.
  ModoFuente get modoFuente => _adjuntos.any((SubidaDocumento a) => a.estaListo)
      ? ModoFuente.conFuente
      : ModoFuente.sinFuente;

  /// Estado de la generación que se está observando.
  EstadoGeneracion? get generacion => _generacion;

  /// Ruta que se está forjando.
  String? get rutaEnGeneracion => _rutaEnGeneracion;

  /// Error del sondeo, si el Reino dejó de responder.
  ErrorAtenea? get errorGeneracion => _errorGeneracion;

  /// ¿Hay un sondeo activo?
  bool get sondeando => _sonda != null;

  /// ¿Ya se puede empezar el Módulo 1 aunque el resto siga en curso?
  bool get primerModuloListo => _generacion?.primerModuloListo ?? false;

  /// La espera superó los diez minutos: P06 cambia el mensaje.
  bool get tardaDemasiado {
    final DateTime? desde = _inicioSondeo;
    if (desde == null) return false;
    return DateTime.now().difference(desde) > esperaLarga;
  }

  /// Mapa de la ruta abierta.
  DetalleRuta? get ruta => _ruta;

  /// Primera carga del mapa.
  bool get cargandoRuta => _cargandoRuta;

  /// Error del mapa.
  ErrorAtenea? get errorRuta => _errorRuta;

  /// Documentos que respaldan la ruta abierta.
  List<Documento> get fuentes => List<Documento>.unmodifiable(_fuentes);

  // -------------------------------------------------------------------------
  // P22 — mis territorios y Rutas del Reino
  // -------------------------------------------------------------------------

  /// Carga las dos listas de P22.
  /// Trae el mapa del Reino: los siete territorios con su estado por usuario.
  ///
  /// **Aparte de `cargarRutas`, y a propósito.** Dentro de su `Future.wait`, un
  /// fallo aquí pondría `_errorRutas` y la pantalla entera diría «El Reino no
  /// responde» aunque las dos listas de rutas hubieran llegado perfectas: se
  /// degradaría una pantalla que funciona por adornar una sección. Aquí un
  /// fallo deja la lista vacía y la sección no se pinta. Nada más.
  ///
  /// Y **su guard mira sus propios datos**, nunca `_mias`. Heredar el de las
  /// rutas dejaría sin refrescar justo al aprendiz que tiene rutas, que es el
  /// único cuyo estado de territorio cambia: haría una lección, volvería, y
  /// vería su castillo igual de apagado que antes.
  Future<void> cargarTerritorios({bool forzar = false}) async {
    if (!forzar && _territorios.isNotEmpty) return;
    try {
      _territorios = (await _repos.conocimiento.territorios()).elementos;
      notifyListeners();
    } catch (_) {
      // Sin territorios no hay sección, y ya está. No es un error de pantalla.
    }
  }

  Future<void> cargarRutas({bool forzar = false}) async {
    if (_cargandoRutas) return;
    if (!forzar && _mias.isNotEmpty) return;
    _cargandoRutas = true;
    _errorRutas = null;
    notifyListeners();
    try {
      final List<Pagina<ResumenRuta>> paginas = await Future.wait(
        <Future<Pagina<ResumenRuta>>>[
          _repos.rutas.rutas(ambito: AmbitoRutas.mias),
          _repos.rutas.rutas(ambito: AmbitoRutas.delReino),
        ],
      );
      _mias = paginas[0].elementos;
      _cursorMias = paginas[0].cursorSiguiente;
      _hayMasMias = paginas[0].info.puedeSeguir;
      _delReino = paginas[1].elementos;
    } catch (e) {
      _errorRutas = _comoError(e);
    } finally {
      _cargandoRutas = false;
      notifyListeners();
    }
  }

  /// Trae la siguiente página de rutas propias (scroll infinito).
  Future<void> masRutasMias() async {
    final String? cursor = _cursorMias;
    if (_cargandoMas || !_hayMasMias || cursor == null) return;
    _cargandoMas = true;
    notifyListeners();
    try {
      final Pagina<ResumenRuta> pagina =
          await _repos.rutas.rutas(ambito: AmbitoRutas.mias, cursor: cursor);
      _mias = <ResumenRuta>[..._mias, ...pagina.elementos];
      _cursorMias = pagina.cursorSiguiente;
      _hayMasMias = pagina.info.puedeSeguir;
    } catch (e) {
      _errorRutas = _comoError(e);
    } finally {
      _cargandoMas = false;
      notifyListeners();
    }
  }

  /// Adopta una Ruta del Reino y la deja disponible como propia.
  Future<DetalleRuta?> adoptar(String rutaId) async {
    try {
      final DetalleRuta adoptada = await _repos.rutas.adoptar(rutaId);
      _ruta = adoptada;
      await cargarRutas(forzar: true);
      return adoptada;
    } catch (e) {
      _errorRutas = _comoError(e);
      notifyListeners();
      return null;
    }
  }

  /// Renombra o archiva una ruta desde el menú de P07/P22.
  Future<bool> actualizarRuta(
    String rutaId, {
    String? titulo,
    bool? archivada,
  }) async {
    try {
      final DetalleRuta actualizada = await _repos.rutas.actualizar(
        rutaId,
        titulo: titulo,
        archivada: archivada,
      );
      if (_ruta?.id == rutaId) _ruta = actualizada;
      await cargarRutas(forzar: true);
      return true;
    } catch (e) {
      _errorRuta = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  /// Elimina una ruta y sus misiones asociadas.
  Future<bool> eliminarRuta(String rutaId) async {
    try {
      await _repos.rutas.eliminar(rutaId);
      if (_ruta?.id == rutaId) _ruta = null;
      _mias = _mias
          .where((ResumenRuta r) => r.id != rutaId)
          .toList(growable: false);
      notifyListeners();
      return true;
    } catch (e) {
      _errorRutas = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  // -------------------------------------------------------------------------
  // P05 — borrador de la nueva ruta
  // -------------------------------------------------------------------------

  /// Escribe el objetivo ("Quiero aprender SQL para analizar datos").
  void fijarObjetivo(String texto) {
    if (_objetivo == texto) return;
    _objetivo = texto;
    notifyListeners();
  }

  /// Elige el nivel declarado.
  void fijarNivel(NivelDeclarado valor) {
    if (_nivel == valor) return;
    _nivel = valor;
    notifyListeners();
  }

  /// Minutos al día que el usuario dice tener (informativo).
  void fijarMinutosAlDia(int minutos) {
    if (_minutosAlDia == minutos) return;
    _minutosAlDia = minutos;
    notifyListeners();
  }

  /// Pista de conocimiento, si la pantalla sugiere un área concreta.
  void fijarPistaConocimiento(String? pista) {
    _pistaConocimiento = pista;
    notifyListeners();
  }

  /// Adjunta un archivo y lo sube con progreso.
  ///
  /// Devuelve `false` y deja el motivo en [avisoArchivo] si el archivo se
  /// rechaza por formato, por tamaño o por exceder el límite del plan.
  Future<bool> agregarArchivo({
    required String nombreArchivo,
    required List<int> bytes,
    String? titulo,
  }) async {
    _avisoArchivo = _revisarArchivo(nombreArchivo, bytes.length);
    if (_avisoArchivo != null) {
      notifyListeners();
      return false;
    }
    final SubidaDocumento adjunto = SubidaDocumento(
      id: claveIdempotencia(),
      nombreArchivo: nombreArchivo,
      bytes: bytes,
      clave: claveIdempotencia(),
      titulo: titulo,
    );
    _adjuntos.add(adjunto);
    notifyListeners();
    await _subir(adjunto);
    return adjunto.estaListo;
  }

  /// Reintenta una subida fallida con **la misma** clave de idempotencia.
  Future<void> reintentarSubida(String id) async {
    for (final SubidaDocumento a in _adjuntos) {
      if (a.id == id) {
        await _subir(a);
        return;
      }
    }
  }

  /// Quita un archivo de la lista del borrador.
  void quitarArchivo(String id) {
    _adjuntos.removeWhere((SubidaDocumento a) => a.id == id);
    _avisoArchivo = null;
    notifyListeners();
  }

  /// Pega texto como material de estudio.
  Future<bool> pegarTexto({
    required String titulo,
    required String texto,
  }) async {
    final SubidaDocumento adjunto = SubidaDocumento(
      id: claveIdempotencia(),
      nombreArchivo: '$titulo.txt',
      bytes: const <int>[],
      clave: claveIdempotencia(),
      titulo: titulo,
    );
    adjunto.estado = EstadoSubida.subiendo;
    _adjuntos.add(adjunto);
    notifyListeners();
    try {
      adjunto.documento = await _repos.documentos.pegar(
        titulo: titulo,
        texto: texto,
        clave: adjunto.clave,
      );
      adjunto.estado = EstadoSubida.listo;
      adjunto.error = null;
      return true;
    } catch (e) {
      adjunto.estado = EstadoSubida.fallida;
      adjunto.error = _comoError(e).mensaje;
      return false;
    } finally {
      notifyListeners();
    }
  }

  /// Envía el borrador y encola la Fase A. Devuelve el identificador de la
  /// Ruta creada, o `null` si falló.
  Future<String?> crearRuta() async {
    if (_creando) return null;
    _creando = true;
    _errorCreacion = null;
    notifyListeners();
    try {
      final List<String> documentos = _adjuntos
          .where((SubidaDocumento a) => a.estaListo)
          .map((SubidaDocumento a) => a.documento!.id)
          .toList(growable: false);
      final RutaCreada creada = await _repos.rutas.crear(
        objetivo: _objetivo,
        nivelDeclarado: _nivel,
        documentos: documentos,
        modoFuente: modoFuente,
        pistaConocimiento: _pistaConocimiento,
        clave: _claveCrear,
      );
      _mias = <ResumenRuta>[creada.ruta, ..._mias];
      return creada.ruta.id;
    } catch (e) {
      _errorCreacion = _comoError(e);
      return null;
    } finally {
      _creando = false;
      notifyListeners();
    }
  }

  /// Vacía el borrador de P05 y genera una clave de idempotencia nueva.
  void reiniciarBorrador() {
    _objetivo = '';
    _nivel = NivelDeclarado.principiante;
    _pistaConocimiento = null;
    _minutosAlDia = 10;
    _adjuntos.clear();
    _claveCrear = claveIdempotencia();
    _errorCreacion = null;
    _avisoArchivo = null;
    notifyListeners();
  }

  // -------------------------------------------------------------------------
  // P06 — estado de la generación
  // -------------------------------------------------------------------------

  /// Empieza a observar la generación de [rutaId]: consulta de inmediato y
  /// luego cada [intervaloSondeo], y se detiene sola al terminar o al fallar.
  void iniciarSondeo(String rutaId) {
    if (_rutaEnGeneracion == rutaId && _sonda != null) return;
    detenerSondeo();
    _rutaEnGeneracion = rutaId;
    _generacion = null;
    _errorGeneracion = null;
    _inicioSondeo = DateTime.now();
    notifyListeners();
    unawaited(_consultarGeneracion());
    _sonda = Timer.periodic(
      intervaloSondeo,
      (Timer _) => unawaited(_consultarGeneracion()),
    );
  }

  /// Corta el sondeo (al salir de P06 o cuando la generación termina).
  void detenerSondeo() {
    _sonda?.cancel();
    _sonda = null;
  }

  /// Vuelve a intentar la generación tras un fallo, reiniciando el reloj.
  Future<void> reintentarGeneracion() async {
    final String? rutaId = _rutaEnGeneracion;
    if (rutaId == null) return;
    _errorGeneracion = null;
    _inicioSondeo = DateTime.now();
    notifyListeners();
    iniciarSondeo(rutaId);
  }

  Future<void> _consultarGeneracion() async {
    final String? rutaId = _rutaEnGeneracion;
    if (rutaId == null) return;
    try {
      final EstadoGeneracion estado = await _repos.rutas.generacion(rutaId);
      _generacion = estado;
      _errorGeneracion = null;
      if (!estado.enMarcha) {
        detenerSondeo();
        if (estado.termino) await abrirRuta(rutaId, forzar: true);
      }
    } catch (e) {
      final ErrorAtenea fallo = _comoError(e);
      _errorGeneracion = fallo;
      // Un corte de red no cancela la forja: solo dejamos de preguntar si el
      // error no admite reintento.
      if (!fallo.esReintentable) detenerSondeo();
    } finally {
      notifyListeners();
    }
  }

  // -------------------------------------------------------------------------
  // P07 — mapa de la ruta
  // -------------------------------------------------------------------------

  /// Abre el mapa de una ruta. Conserva el mapa anterior si la petición falla.
  Future<void> abrirRuta(String rutaId, {bool forzar = false}) async {
    if (!forzar && _ruta?.id == rutaId) return;
    _cargandoRuta = _ruta?.id != rutaId;
    _errorRuta = null;
    notifyListeners();
    try {
      _ruta = await _repos.rutas.ruta(rutaId);
    } catch (e) {
      _errorRuta = _comoError(e);
    } finally {
      _cargandoRuta = false;
      notifyListeners();
    }
  }

  /// Confirma el esquema revisado y encola el Módulo 1.
  Future<bool> confirmarEsquema(
    String rutaId, {
    List<AjusteTema> temas = const <AjusteTema>[],
    PoliticaCobertura? politicaCobertura,
  }) async {
    try {
      _ruta = await _repos.rutas.confirmar(
        rutaId,
        temas: temas,
        politicaCobertura: politicaCobertura,
      );
      notifyListeners();
      return true;
    } catch (e) {
      _errorRuta = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  /// Carga los documentos que respaldan la ruta abierta.
  Future<void> cargarFuentes(String rutaId) async {
    try {
      final Pagina<Documento> pagina = await _repos.rutas.fuentes(rutaId);
      _fuentes = pagina.elementos;
      _errorRuta = null;
    } catch (e) {
      _errorRuta = _comoError(e);
    }
    notifyListeners();
  }

  /// Olvida todo al cerrar sesión.
  void limpiar() {
    detenerSondeo();
    _mias = const <ResumenRuta>[];
    _delReino = const <ResumenRuta>[];
    _territorios = const <Territorio>[];
    _cursorMias = null;
    _hayMasMias = false;
    _ruta = null;
    _fuentes = const <Documento>[];
    _generacion = null;
    _rutaEnGeneracion = null;
    _inicioSondeo = null;
    reiniciarBorrador();
  }

  @override
  void dispose() {
    detenerSondeo();
    super.dispose();
  }

  // -------------------------------------------------------------------------
  // Interno
  // -------------------------------------------------------------------------

  Future<void> _subir(SubidaDocumento adjunto) async {
    adjunto.estado = EstadoSubida.subiendo;
    adjunto.enviados = 0;
    adjunto.error = null;
    notifyListeners();
    try {
      adjunto.documento = await _repos.documentos.subir(
        bytes: adjunto.bytes,
        nombreArchivo: adjunto.nombreArchivo,
        titulo: adjunto.titulo,
        clave: adjunto.clave,
        alProgresar: (int enviados, int total) {
          adjunto.enviados = enviados;
          notifyListeners();
        },
      );
      adjunto.enviados = adjunto.total;
      adjunto.estado = EstadoSubida.listo;
    } catch (e) {
      adjunto.estado = EstadoSubida.fallida;
      adjunto.error = _comoError(e).mensaje;
    } finally {
      notifyListeners();
    }
  }

  /// Devuelve el motivo del rechazo, o `null` si el archivo es admisible.
  String? _revisarArchivo(String nombreArchivo, int tamano) {
    final int punto = nombreArchivo.lastIndexOf('.');
    final String extension =
        punto < 0 ? '' : nombreArchivo.substring(punto + 1).toLowerCase();
    if (!extensionesPermitidas.contains(extension)) {
      return 'Por ahora leemos PDF, DOCX, TXT y MD. Ese archivo no podemos '
          'abrirlo todavía.';
    }
    if (_adjuntos.length >= maxArchivos) {
      return 'Puedes adjuntar hasta $maxArchivos archivos por ruta. Quita '
          'alguno para agregar otro.';
    }
    if (bytesAdjuntos + tamano > maxBytesTotales) {
      return 'Entre todos los archivos caben 50 MB. Este se pasa del límite.';
    }
    if (tamano <= 0) {
      return 'Ese archivo llegó vacío. Prueba con otro.';
    }
    return null;
  }
}

/// Traduce cualquier fallo a un [ErrorAtenea] con mensaje en español.
ErrorAtenea _comoError(Object error) => error is ErrorAtenea
    ? error
    : const ErrorAtenea(
        codigo: 'inesperado',
        mensaje: 'Ocurrió algo inesperado. Inténtalo de nuevo.',
      );
