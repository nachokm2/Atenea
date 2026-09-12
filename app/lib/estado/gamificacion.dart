/// Estado de la gamificación: Misiones (P19), Logros (P20), Racha y
/// calendario (P18), objetivo diario y notificaciones.
///
/// Las recompensas de misión se otorgan solas en el servidor; [reclamarMision]
/// existe solo para las plantillas que exigen reclamo explícito, y devuelve un
/// [ReciboRecompensas] que se encola en la cola de celebraciones.
library;

import 'package:flutter/foundation.dart';

import '../data/errores.dart';
import '../datos/repositorios.dart';

/// Misiones, logros, racha, objetivo diario y notificaciones.
class ControladorGamificacion extends ChangeNotifier {
  ControladorGamificacion(this._repos);

  final Repositorios _repos;

  // --- Misiones ------------------------------------------------------------
  Misiones? _misiones;
  bool _cargandoMisiones = false;
  ErrorAtenea? _errorMisiones;
  AmbitoMision _pestanaMisiones = AmbitoMision.diaria;
  String? _reclamando;

  // --- Racha y objetivo ----------------------------------------------------
  Racha? _racha;
  CalendarioRacha? _calendario;
  String? _mesCalendario;
  ObjetivoDiario? _objetivo;
  bool _cargandoRacha = false;
  bool _guardandoObjetivo = false;
  ErrorAtenea? _errorRacha;

  // --- Logros --------------------------------------------------------------
  List<Logro> _logros = const <Logro>[];
  String? _cursorLogros;
  bool _hayMasLogros = false;
  bool _cargandoLogros = false;
  bool _cargandoMasLogros = false;
  ErrorAtenea? _errorLogros;
  FiltroLogros _filtroLogros = FiltroLogros.todos;
  CategoriaLogro? _categoriaLogros;

  // --- Notificaciones ------------------------------------------------------
  List<Notificacion> _notificaciones = const <Notificacion>[];
  String? _cursorNotificaciones;
  bool _hayMasNotificaciones = false;
  bool _cargandoNotificaciones = false;
  ErrorAtenea? _errorNotificaciones;

  // -------------------------------------------------------------------------
  // Lecturas — misiones
  // -------------------------------------------------------------------------

  /// Misiones diarias, semanales y de ruta.
  Misiones? get misiones => _misiones;

  /// Pestaña visible de P19.
  AmbitoMision get pestanaMisiones => _pestanaMisiones;

  /// Misiones de la pestaña visible.
  List<Mision> get misionesVisibles =>
      _misiones?.porAmbito(_pestanaMisiones) ?? const <Mision>[];

  /// Carga de misiones en curso.
  bool get cargandoMisiones => _cargandoMisiones;

  /// Error de misiones.
  ErrorAtenea? get errorMisiones => _errorMisiones;

  /// Misión que se está reclamando ahora mismo.
  String? get misionReclamando => _reclamando;

  /// Segundos que faltan para el reinicio de medianoche local.
  int get segundosParaReinicio => _misiones?.segundosParaReinicio ?? 0;

  // -------------------------------------------------------------------------
  // Lecturas — racha y objetivo
  // -------------------------------------------------------------------------

  /// Racha vigente.
  Racha get racha => _racha ?? const Racha();

  /// Calendario del mes cargado.
  CalendarioRacha? get calendario => _calendario;

  /// Mes del calendario, en formato `2026-09`.
  String? get mesCalendario => _mesCalendario;

  /// Objetivo diario vigente.
  ObjetivoDiario get objetivoDiario => _objetivo ?? const ObjetivoDiario();

  /// Recomendación adaptativa del objetivo, si el Reino propone cambiarlo.
  RecomendacionObjetivo? get recomendacion => _objetivo?.recomendacion;

  /// Carga de racha y objetivo en curso.
  bool get cargandoRacha => _cargandoRacha;

  /// Guardando el objetivo diario.
  bool get guardandoObjetivo => _guardandoObjetivo;

  /// Error de racha u objetivo.
  ErrorAtenea? get errorRacha => _errorRacha;

  // -------------------------------------------------------------------------
  // Lecturas — logros
  // -------------------------------------------------------------------------

  /// Logros cargados con los filtros vigentes.
  List<Logro> get logros => List<Logro>.unmodifiable(_logros);

  /// Cuántos están desbloqueados de los cargados.
  int get logrosDesbloqueados =>
      _logros.where((Logro l) => l.estaDesbloqueado).length;

  /// ¿Quedan más páginas?
  bool get hayMasLogros => _hayMasLogros;

  /// Primera carga de logros.
  bool get cargandoLogros => _cargandoLogros;

  /// Trayendo más logros.
  bool get cargandoMasLogros => _cargandoMasLogros;

  /// Error de logros.
  ErrorAtenea? get errorLogros => _errorLogros;

  /// Filtro activo de la sala de trofeos.
  FiltroLogros get filtroLogros => _filtroLogros;

  /// Categoría activa.
  CategoriaLogro? get categoriaLogros => _categoriaLogros;

  // -------------------------------------------------------------------------
  // Lecturas — notificaciones
  // -------------------------------------------------------------------------

  /// Notificaciones recibidas, de la más reciente a la más antigua.
  List<Notificacion> get notificaciones =>
      List<Notificacion>.unmodifiable(_notificaciones);

  /// Cuántas siguen sin leer.
  int get sinLeer => _notificaciones.where((Notificacion n) => !n.estaLeida).length;

  /// ¿Quedan más notificaciones?
  bool get hayMasNotificaciones => _hayMasNotificaciones;

  /// Carga de notificaciones en curso.
  bool get cargandoNotificaciones => _cargandoNotificaciones;

  /// Error de notificaciones.
  ErrorAtenea? get errorNotificaciones => _errorNotificaciones;

  // -------------------------------------------------------------------------
  // Misiones
  // -------------------------------------------------------------------------

  /// Trae las misiones de P19.
  Future<void> cargarMisiones({bool forzar = false}) async {
    if (_cargandoMisiones) return;
    if (!forzar && _misiones != null) return;
    _cargandoMisiones = true;
    _errorMisiones = null;
    notifyListeners();
    try {
      _misiones = await _repos.gamificacion.misiones();
    } catch (e) {
      _errorMisiones = _comoError(e);
    } finally {
      _cargandoMisiones = false;
      notifyListeners();
    }
  }

  /// Cambia la pestaña de P19.
  void fijarPestanaMisiones(AmbitoMision ambito) {
    if (_pestanaMisiones == ambito) return;
    _pestanaMisiones = ambito;
    notifyListeners();
  }

  /// Reclama una misión cumplida y devuelve su recibo para celebrarlo.
  Future<ReciboRecompensas?> reclamarMision(String misionId) async {
    if (_reclamando != null) return null;
    _reclamando = misionId;
    _errorMisiones = null;
    notifyListeners();
    try {
      final ReciboRecompensas recibo = await _repos.gamificacion.reclamarMision(
        misionId,
        clave: claveDeterminista('mission-claim', misionId),
      );
      await cargarMisiones(forzar: true);
      return recibo;
    } catch (e) {
      _errorMisiones = _comoError(e);
      return null;
    } finally {
      _reclamando = null;
      notifyListeners();
    }
  }

  // -------------------------------------------------------------------------
  // Racha, calendario y objetivo diario
  // -------------------------------------------------------------------------

  /// Trae racha, calendario del mes pedido y objetivo diario de P18.
  Future<void> cargarRacha({String? mes, bool forzar = false}) async {
    if (_cargandoRacha) return;
    final String objetivoMes = mes ?? _mesCalendario ?? _mesDeHoy();
    if (!forzar && _racha != null && _mesCalendario == objetivoMes) return;
    _cargandoRacha = true;
    _errorRacha = null;
    notifyListeners();
    try {
      _racha = await _repos.gamificacion.racha();
      _calendario = await _repos.gamificacion.calendario(mes: objetivoMes);
      _mesCalendario = objetivoMes;
      _objetivo = await _repos.gamificacion.objetivoDiario();
    } catch (e) {
      _errorRacha = _comoError(e);
    } finally {
      _cargandoRacha = false;
      notifyListeners();
    }
  }

  /// Cambia el mes del calendario.
  Future<void> cambiarMes(String mes) => cargarRacha(mes: mes, forzar: true);

  /// Cambia la intensidad del objetivo diario (Ligero / Normal / Intenso).
  Future<bool> cambiarObjetivo({
    required TipoObjetivo tipo,
    required int meta,
  }) async {
    if (_guardandoObjetivo) return false;
    _guardandoObjetivo = true;
    _errorRacha = null;
    notifyListeners();
    try {
      _objetivo = await _repos.gamificacion.cambiarObjetivo(
        tipo: tipo,
        meta: meta,
      );
      return true;
    } catch (e) {
      _errorRacha = _comoError(e);
      return false;
    } finally {
      _guardandoObjetivo = false;
      notifyListeners();
    }
  }

  /// Acepta la recomendación adaptativa del Reino.
  Future<bool> aceptarRecomendacion() async {
    try {
      _objetivo = await _repos.gamificacion.aceptarRecomendacion();
      notifyListeners();
      return true;
    } catch (e) {
      _errorRacha = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  /// Descarta la recomendación sin cambiar el objetivo.
  Future<void> descartarRecomendacion() async {
    try {
      await _repos.gamificacion.descartarRecomendacion();
      _objetivo = await _repos.gamificacion.objetivoDiario();
    } catch (e) {
      _errorRacha = _comoError(e);
    }
    notifyListeners();
  }

  // -------------------------------------------------------------------------
  // Logros
  // -------------------------------------------------------------------------

  /// Trae la primera página de logros con los filtros vigentes.
  Future<void> cargarLogros({bool forzar = false}) async {
    if (_cargandoLogros) return;
    if (!forzar && _logros.isNotEmpty) return;
    _cargandoLogros = true;
    _errorLogros = null;
    notifyListeners();
    try {
      final Pagina<Logro> pagina = await _repos.gamificacion.logros(
        filtro: _filtroLogros,
        categoria: _categoriaLogros,
      );
      _logros = pagina.elementos;
      _cursorLogros = pagina.cursorSiguiente;
      _hayMasLogros = pagina.info.puedeSeguir;
    } catch (e) {
      _errorLogros = _comoError(e);
    } finally {
      _cargandoLogros = false;
      notifyListeners();
    }
  }

  /// Trae la siguiente página de logros.
  Future<void> masLogros() async {
    final String? cursor = _cursorLogros;
    if (_cargandoMasLogros || !_hayMasLogros || cursor == null) return;
    _cargandoMasLogros = true;
    notifyListeners();
    try {
      final Pagina<Logro> pagina = await _repos.gamificacion.logros(
        filtro: _filtroLogros,
        categoria: _categoriaLogros,
        cursor: cursor,
      );
      _logros = <Logro>[..._logros, ...pagina.elementos];
      _cursorLogros = pagina.cursorSiguiente;
      _hayMasLogros = pagina.info.puedeSeguir;
    } catch (e) {
      _errorLogros = _comoError(e);
    } finally {
      _cargandoMasLogros = false;
      notifyListeners();
    }
  }

  /// Cambia el filtro Todos / Desbloqueados / En progreso.
  Future<void> fijarFiltroLogros(FiltroLogros filtro) async {
    if (_filtroLogros == filtro) return;
    _filtroLogros = filtro;
    notifyListeners();
    await cargarLogros(forzar: true);
  }

  /// Cambia la categoría de la sala de trofeos.
  Future<void> fijarCategoriaLogros(CategoriaLogro? categoria) async {
    if (_categoriaLogros == categoria) return;
    _categoriaLogros = categoria;
    notifyListeners();
    await cargarLogros(forzar: true);
  }

  // -------------------------------------------------------------------------
  // Notificaciones
  // -------------------------------------------------------------------------

  /// Trae la bandeja de notificaciones.
  Future<void> cargarNotificaciones({bool forzar = false}) async {
    if (_cargandoNotificaciones) return;
    if (!forzar && _notificaciones.isNotEmpty) return;
    _cargandoNotificaciones = true;
    _errorNotificaciones = null;
    notifyListeners();
    try {
      final Pagina<Notificacion> pagina =
          await _repos.gamificacion.notificaciones();
      _notificaciones = pagina.elementos;
      _cursorNotificaciones = pagina.cursorSiguiente;
      _hayMasNotificaciones = pagina.info.puedeSeguir;
    } catch (e) {
      _errorNotificaciones = _comoError(e);
    } finally {
      _cargandoNotificaciones = false;
      notifyListeners();
    }
  }

  /// Trae la siguiente página de notificaciones.
  Future<void> masNotificaciones() async {
    final String? cursor = _cursorNotificaciones;
    if (!_hayMasNotificaciones || cursor == null) return;
    try {
      final Pagina<Notificacion> pagina =
          await _repos.gamificacion.notificaciones(cursor: cursor);
      _notificaciones = <Notificacion>[..._notificaciones, ...pagina.elementos];
      _cursorNotificaciones = pagina.cursorSiguiente;
      _hayMasNotificaciones = pagina.info.puedeSeguir;
    } catch (e) {
      _errorNotificaciones = _comoError(e);
    }
    notifyListeners();
  }

  /// Marca una notificación como leída.
  Future<void> marcarLeida(String notificacionId) async {
    try {
      await _repos.gamificacion.marcarLeida(notificacionId);
      await cargarNotificaciones(forzar: true);
    } catch (e) {
      _errorNotificaciones = _comoError(e);
      notifyListeners();
    }
  }

  /// Marca todas como leídas.
  Future<void> marcarTodasLeidas() async {
    try {
      await _repos.gamificacion.marcarTodasLeidas();
      await cargarNotificaciones(forzar: true);
    } catch (e) {
      _errorNotificaciones = _comoError(e);
      notifyListeners();
    }
  }

  /// Registra el token de push del dispositivo.
  Future<void> registrarTokenPush(String token, {String? plataforma}) async {
    try {
      await _repos.gamificacion.registrarTokenPush(token, plataforma: plataforma);
    } catch (_) {
      // Sin push el aprendizaje sigue funcionando: no se avisa.
    }
  }

  /// Olvida todo al cerrar sesión.
  void limpiar() {
    _misiones = null;
    _racha = null;
    _calendario = null;
    _mesCalendario = null;
    _objetivo = null;
    _logros = const <Logro>[];
    _cursorLogros = null;
    _hayMasLogros = false;
    _notificaciones = const <Notificacion>[];
    _cursorNotificaciones = null;
    _hayMasNotificaciones = false;
    _errorMisiones = null;
    _errorRacha = null;
    _errorLogros = null;
    _errorNotificaciones = null;
    notifyListeners();
  }

  static String _mesDeHoy() {
    final DateTime hoy = DateTime.now();
    return '${hoy.year.toString().padLeft(4, '0')}-'
        '${hoy.month.toString().padLeft(2, '0')}';
  }
}

/// Traduce cualquier fallo a un [ErrorAtenea] con mensaje en español.
ErrorAtenea _comoError(Object error) => error is ErrorAtenea
    ? error
    : const ErrorAtenea(
        codigo: 'inesperado',
        mensaje: 'Ocurrió algo inesperado. Inténtalo de nuevo.',
      );
