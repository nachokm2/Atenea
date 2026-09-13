/// Estado de la sesión: arranque, acceso al Reino y onboarding.
///
/// Este controlador es la única fuente de verdad sobre "quién está dentro":
/// el enrutador lo escucha (`refreshListenable`) y decide con [fase] si hay
/// que mandar a la entrada (P01/P02), a la creación de personaje (P03) o al
/// Inicio (P04).
library;

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/almacen_tokens.dart';
import '../data/api_client.dart';
import '../data/errores.dart';
import '../datos/repositorios.dart';

/// Fase del arranque y de la sesión, en el orden en que ocurren.
enum FaseSesion {
  /// Todavía se están leyendo los tokens y pidiendo `/auth/me`.
  arrancando,

  /// No hay tokens válidos: hay que registrarse o entrar.
  sinSesion,

  /// Hay cuenta pero aún no hay personaje: falta P03.
  sinPersonaje,

  /// Sesión completa: la app puede navegar con normalidad.
  lista,
}

/// Sesión, cuenta, personaje y preferencias en memoria.
class ControladorSesion extends ChangeNotifier {
  ControladorSesion({
    required Repositorios repositorios,
    required AlmacenTokens tokens,
  })  : _repos = repositorios,
        _tokens = tokens;

  /// Preferencia local: ¿ya se vio el onboarding de P01?
  static const String _claveOnboarding = 'atenea_onboarding_visto';

  final Repositorios _repos;
  final AlmacenTokens _tokens;

  FaseSesion _fase = FaseSesion.arrancando;
  Usuario? _usuario;
  Personaje? _personaje;
  Ajustes? _ajustes;
  bool _tieneRuta = false;
  bool _ocupado = false;
  bool _onboardingVisto = false;
  ErrorAtenea? _error;

  /// Fase vigente; el enrutador redirige a partir de ella.
  FaseSesion get fase => _fase;

  /// Cuenta autenticada, si la hay.
  Usuario? get usuario => _usuario;

  /// Personaje del héroe, si ya lo creó.
  Personaje? get personaje => _personaje;

  /// Preferencias vigentes (tema, movimiento reducido, avisos…).
  Ajustes? get ajustes => _ajustes;

  /// ¿Ya tiene al menos una Ruta? Lo usa el Inicio para el estado "sin rutas".
  bool get tieneRuta => _tieneRuta;

  /// ¿Hay una petición de acceso en curso? Deshabilita el formulario de P02.
  bool get ocupado => _ocupado;

  /// Último error del acceso, ya en español.
  ErrorAtenea? get error => _error;

  /// ¿Se vio el onboarding de bienvenida alguna vez en este dispositivo?
  bool get onboardingVisto => _onboardingVisto;

  /// ¿Hay una sesión utilizable (con o sin personaje)?
  bool get haySesion =>
      _fase == FaseSesion.sinPersonaje || _fase == FaseSesion.lista;

  /// `true` cuando entramos con tokens guardados pero `/auth/me` no respondió:
  /// el Inicio muestra el aviso discreto y ofrece reintentar.
  bool get arranqueIncompleto => _usuario == null && _error != null;

  /// Nombre con el que saludar; cae al correo y luego a "héroe".
  String get nombreVisible {
    final String nombre = _personaje?.nombre ?? '';
    if (nombre.isNotEmpty) return nombre;
    final String correo = _usuario?.correo ?? '';
    if (correo.isEmpty) return 'héroe';
    final int arroba = correo.indexOf('@');
    return arroba > 0 ? correo.substring(0, arroba) : correo;
  }

  /// Arranque de la aplicación: lee la preferencia de onboarding, carga los
  /// tokens y, si los hay, pide `/auth/me`.
  Future<void> arrancar() async {
    _onboardingVisto = await _leerOnboarding();
    await _tokens.cargar();
    if (!_tokens.haySesion) {
      _fase = FaseSesion.sinSesion;
      notifyListeners();
      return;
    }
    await _cargarYo();
  }

  /// Crea la cuenta (P02) y deja al usuario en la creación de personaje.
  Future<bool> registrar({
    required String correo,
    required String contrasena,
  }) async {
    return _acceder(
      () => _repos.auth.registrar(
        correo: correo,
        contrasena: contrasena,
        // Solo si el sistema sabe decirla en forma IANA: guardar el nombre
        // localizado ("Hora verano Sudamérica Pacífico") dejaría al perfil con
        // una zona que el Reino no reconoce y que el aprendiz vería en Ajustes.
        zonaHoraria: ApiClient.zonaDelSistema(),
        idioma: 'es-CL',
      ),
    );
  }

  /// Inicia sesión con correo y contraseña (P02).
  Future<bool> entrar({
    required String correo,
    required String contrasena,
  }) async {
    return _acceder(
      () => _repos.auth.entrar(correo: correo, contrasena: contrasena),
    );
  }

  /// Cierra la sesión revocando el token de refresco.
  Future<void> salir() async {
    final String? refresco = _tokens.refresco;
    if (refresco != null && refresco.isNotEmpty) {
      try {
        await _repos.auth.salir(refresco);
      } catch (_) {
        // Si el servidor no responde igualmente cerramos en el dispositivo:
        // el token de acceso caduca solo.
      }
    }
    await _olvidar();
  }

  /// Vuelve a pedir `/auth/me`. Lo usa el Inicio al reintentar y P03 al
  /// terminar la creación del personaje.
  Future<void> refrescarYo() => _cargarYo();

  /// Lo llama el [ApiClient] cuando el refresco falla: la sesión murió.
  void alPerderSesion() {
    if (_fase == FaseSesion.sinSesion) return;
    _usuario = null;
    _personaje = null;
    _ajustes = null;
    _tieneRuta = false;
    _fase = FaseSesion.sinSesion;
    _error = const ErrorAtenea(
      codigo: 'sesion_expirada',
      mensaje: 'Tu sesión expiró. Vuelve a entrar al Reino.',
      estadoHttp: 401,
    );
    notifyListeners();
  }

  /// Registra el personaje recién creado en P03 y abre el Reino.
  void anotarPersonaje(Personaje nuevo) {
    _personaje = nuevo;
    _fase = FaseSesion.lista;
    _error = null;
    notifyListeners();
  }

  /// Refresca el personaje tras un cambio de nombre, de Orden o de nivel.
  void actualizarPersonaje(Personaje? actual) {
    if (actual == null) return;
    _personaje = actual;
    notifyListeners();
  }

  /// Marca que ya existe al menos una Ruta (tras crear o adoptar una).
  void anotarRuta() {
    if (_tieneRuta) return;
    _tieneRuta = true;
    notifyListeners();
  }

  /// Deja constancia de que el onboarding de P01 ya se vio.
  Future<void> marcarOnboardingVisto() async {
    if (_onboardingVisto) return;
    _onboardingVisto = true;
    notifyListeners();
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_claveOnboarding, true);
    } catch (_) {
      // Si no se puede persistir, el onboarding se volverá a ver: es
      // molesto, no grave.
    }
  }

  /// Cambia la contraseña desde Ajustes (P21).
  Future<bool> cambiarContrasena({
    required String actual,
    required String nueva,
  }) async {
    _ocupado = true;
    _error = null;
    notifyListeners();
    try {
      await _repos.auth.cambiarContrasena(actual: actual, nueva: nueva);
      return true;
    } catch (e) {
      _error = _comoError(e);
      return false;
    } finally {
      _ocupado = false;
      notifyListeners();
    }
  }

  /// Elimina la cuenta (P21) y cierra la sesión en el dispositivo.
  Future<bool> eliminarCuenta() async {
    _ocupado = true;
    _error = null;
    notifyListeners();
    try {
      await _repos.auth.eliminarCuenta();
      await _olvidar();
      return true;
    } catch (e) {
      _error = _comoError(e);
      return false;
    } finally {
      _ocupado = false;
      notifyListeners();
    }
  }

  /// Pide el enlace de recuperación. Devuelve `true` si la petición salió.
  ///
  /// Un `true` **no** significa que exista la cuenta: el Reino responde igual en
  /// los dos casos a propósito, y la pantalla dice lo mismo siempre.
  Future<bool> pedirRecuperacion(String correo) async {
    _ocupado = true;
    _error = null;
    notifyListeners();
    try {
      await _repos.auth.pedirRecuperacion(correo);
      return true;
    } catch (e) {
      _error = _comoError(e);
      return false;
    } finally {
      _ocupado = false;
      notifyListeners();
    }
  }

  /// Elige la contraseña nueva con el permiso recibido por correo.
  Future<bool> restablecerContrasena({
    required String permiso,
    required String nueva,
  }) async {
    _ocupado = true;
    _error = null;
    notifyListeners();
    try {
      await _repos.auth.restablecerContrasena(permiso: permiso, nueva: nueva);
      return true;
    } catch (e) {
      _error = _comoError(e);
      return false;
    } finally {
      _ocupado = false;
      notifyListeners();
    }
  }

  /// Relee las preferencias del servidor.
  Future<void> cargarAjustes() async {
    try {
      _ajustes = await _repos.auth.ajustes();
      _anotarZonaHoraria();
      _error = null;
    } catch (e) {
      _error = _comoError(e);
    }
    notifyListeners();
  }

  /// Guarda preferencias de P21. Solo viajan los campos que cambian.
  Future<bool> guardarAjustes({
    PreferenciaTema? tema,
    bool? reducirMovimiento,
    bool? sonidoActivado,
    bool? hapticaActivada,
    bool? pushActivado,
    ModoRecordatorio? modoRecordatorio,
    HoraLocal? horaRecordatorio,
    bool? ultimaLlamadaActivada,
    HoraLocal? silencioDesde,
    HoraLocal? silencioHasta,
    bool? avisarRutaLista,
    bool? avisarRacha,
    bool? avisarMisiones,
    String? idiomaContenido,
    String? zonaHoraria,
    String? idioma,
  }) async {
    try {
      _ajustes = await _repos.auth.actualizarAjustes(
        tema: tema,
        reducirMovimiento: reducirMovimiento,
        sonidoActivado: sonidoActivado,
        hapticaActivada: hapticaActivada,
        pushActivado: pushActivado,
        modoRecordatorio: modoRecordatorio,
        horaRecordatorio: horaRecordatorio,
        ultimaLlamadaActivada: ultimaLlamadaActivada,
        silencioDesde: silencioDesde,
        silencioHasta: silencioHasta,
        avisarRutaLista: avisarRutaLista,
        avisarRacha: avisarRacha,
        avisarMisiones: avisarMisiones,
        idiomaContenido: idiomaContenido,
        zonaHoraria: zonaHoraria,
        idioma: idioma,
      );
      _anotarZonaHoraria();
      _error = null;
      notifyListeners();
      return true;
    } catch (e) {
      _error = _comoError(e);
      notifyListeners();
      return false;
    }
  }

  /// Le pasa al cliente HTTP la zona horaria que el aprendiz tiene guardada.
  ///
  /// El Reino decide con ella de qué día es cada actividad, y de eso dependen
  /// la racha y las misiones diarias. Fuera de un móvil el sistema no siempre
  /// sabe decir su zona en forma IANA (un Windows en español devuelve "Hora
  /// verano Sudamérica Pacífico"), así que el dato del perfil manda.
  void _anotarZonaHoraria() {
    final String? zona = _ajustes?.zonaHoraria;
    if (zona != null && zona.isNotEmpty) {
      _repos.cliente.zonaHorariaIana = zona;
    }
  }

  /// Borra el último error para que el formulario deje de mostrarlo.
  void limpiarError() {
    if (_error == null) return;
    _error = null;
    notifyListeners();
  }

  // -------------------------------------------------------------------------
  // Interno
  // -------------------------------------------------------------------------

  Future<bool> _acceder(Future<TokensAuth> Function() peticion) async {
    _ocupado = true;
    _error = null;
    notifyListeners();
    try {
      final TokensAuth par = await peticion();
      if (!par.esValido) {
        _error = const ErrorAtenea(
          codigo: 'sin_token',
          mensaje: 'El Reino no devolvió tu llave de acceso. Inténtalo otra vez.',
        );
        return false;
      }
      await _tokens.guardar(acceso: par.acceso, refresco: par.refresco);
      _usuario = par.usuario ?? _usuario;
      await _cargarYo();
      return haySesion;
    } catch (e) {
      _error = _comoError(e);
      _fase = FaseSesion.sinSesion;
      return false;
    } finally {
      _ocupado = false;
      notifyListeners();
    }
  }

  Future<void> _cargarYo() async {
    try {
      final Yo yo = await _repos.auth.yo();
      _usuario = yo.usuario ?? _usuario;
      _personaje = yo.personaje ?? _personaje;
      _ajustes = yo.ajustes ?? _ajustes;
      _anotarZonaHoraria();
      _tieneRuta = yo.tieneRuta;
      _error = null;
      _fase = yo.tienePersonaje ? FaseSesion.lista : FaseSesion.sinPersonaje;
    } catch (e) {
      final ErrorAtenea traducido = _comoError(e);
      if (traducido.requiereReautenticar) {
        await _olvidar();
        return;
      }
      // Sin red al arrancar: dejamos entrar con lo que haya en memoria; el
      // Inicio mostrará el aviso discreto y el botón de reintento.
      _error = traducido;
      _fase = FaseSesion.lista;
    }
    notifyListeners();
  }

  Future<void> _olvidar() async {
    await _tokens.limpiar();
    _usuario = null;
    _personaje = null;
    _ajustes = null;
    _tieneRuta = false;
    _error = null;
    _fase = FaseSesion.sinSesion;
    notifyListeners();
  }

  Future<bool> _leerOnboarding() async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      return prefs.getBool(_claveOnboarding) ?? false;
    } catch (_) {
      // Sin preferencias disponibles se asume que no se vio nunca.
      return false;
    }
  }
}

/// Traduce cualquier fallo a un [ErrorAtenea] con mensaje en español.
ErrorAtenea _comoError(Object error) => error is ErrorAtenea
    ? error
    : const ErrorAtenea(
        codigo: 'inesperado',
        mensaje: 'Ocurrió algo inesperado. Inténtalo de nuevo.',
      );
