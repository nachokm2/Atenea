import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Guarda los tokens de sesión.
///
/// En móvil usa el almacenamiento seguro del sistema (Keychain en iOS,
/// EncryptedSharedPreferences en Android). En web, donde no existe un almacén
/// seguro real, recurre a `SharedPreferences`; es una limitación conocida del
/// navegador y por eso el token de acceso es de vida corta.
class AlmacenTokens {
  AlmacenTokens({FlutterSecureStorage? seguro})
      : _seguro = seguro ?? const FlutterSecureStorage();

  static const String _claveAcceso = 'atenea_token_acceso';
  static const String _claveRefresco = 'atenea_token_refresco';

  final FlutterSecureStorage _seguro;

  /// Copia en memoria para evitar una lectura de disco en cada petición.
  String? _accesoEnMemoria;
  String? _refrescoEnMemoria;
  bool _cargado = false;

  bool get usaAlmacenSeguro => !kIsWeb;

  Future<void> cargar() async {
    if (_cargado) return;
    if (usaAlmacenSeguro) {
      _accesoEnMemoria = await _seguro.read(key: _claveAcceso);
      _refrescoEnMemoria = await _seguro.read(key: _claveRefresco);
    } else {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      _accesoEnMemoria = prefs.getString(_claveAcceso);
      _refrescoEnMemoria = prefs.getString(_claveRefresco);
    }
    _cargado = true;
  }

  String? get acceso => _accesoEnMemoria;

  String? get refresco => _refrescoEnMemoria;

  bool get haySesion => (_accesoEnMemoria ?? '').isNotEmpty;

  Future<void> guardar({required String acceso, required String refresco}) async {
    _accesoEnMemoria = acceso;
    _refrescoEnMemoria = refresco;
    _cargado = true;
    if (usaAlmacenSeguro) {
      await _seguro.write(key: _claveAcceso, value: acceso);
      await _seguro.write(key: _claveRefresco, value: refresco);
    } else {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString(_claveAcceso, acceso);
      await prefs.setString(_claveRefresco, refresco);
    }
  }

  /// Reemplaza solo el token de acceso tras un refresco exitoso.
  Future<void> actualizarAcceso(String acceso) async {
    _accesoEnMemoria = acceso;
    if (usaAlmacenSeguro) {
      await _seguro.write(key: _claveAcceso, value: acceso);
    } else {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString(_claveAcceso, acceso);
    }
  }

  Future<void> limpiar() async {
    _accesoEnMemoria = null;
    _refrescoEnMemoria = null;
    if (usaAlmacenSeguro) {
      await _seguro.delete(key: _claveAcceso);
      await _seguro.delete(key: _claveRefresco);
    } else {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.remove(_claveAcceso);
      await prefs.remove(_claveRefresco);
    }
  }
}
