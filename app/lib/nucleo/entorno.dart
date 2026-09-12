import 'package:flutter/foundation.dart';

/// Configuración de entorno del cliente.
///
/// La URL de la API se define al compilar, sin recompilar código:
///
/// ```
/// flutter run --dart-define=ATENEA_API=http://192.168.1.20:8000/api/v1
/// ```
///
/// Si no se define, se elige un valor por defecto sensato según la plataforma:
/// en el emulador de Android `localhost` apunta al propio emulador, por lo que
/// hay que usar `10.0.2.2` para alcanzar la máquina de desarrollo.
abstract final class Entorno {
  static const String _apiDefinida = String.fromEnvironment('ATENEA_API');

  /// URL base de la API, incluyendo el prefijo de versión.
  static String get apiBase {
    if (_apiDefinida.isNotEmpty) return _apiDefinida;
    if (kIsWeb) return 'http://localhost:8000/api/v1';
    return switch (defaultTargetPlatform) {
      TargetPlatform.android => 'http://10.0.2.2:8000/api/v1',
      _ => 'http://localhost:8000/api/v1',
    };
  }

  /// Esquema de los enlaces profundos que abren la app desde una
  /// notificación: `atenea://home`, `atenea://route/{id}`, etc.
  static const String esquemaEnlaces = 'atenea';

  static bool get esDesarrollo => kDebugMode;
}
