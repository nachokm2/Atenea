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

  /// URL de producción. Se usa en cualquier compilación de release que no
  /// traiga `ATENEA_API`, y es **https** a propósito: desde Android 9 el
  /// tráfico en claro está bloqueado, así que un `http://` en release no
  /// fallaría con un error claro, simplemente no respondería nunca.
  ///
  /// Apunta al dominio que **Railway genera** para el servicio, y eso tiene una
  /// consecuencia que conviene saber antes de publicar: va atado al servicio, y
  /// si algún día se recrea, cambia. Una URL metida en un APK ya instalado no se
  /// puede cambiar a distancia, así que antes de dar la aplicación a alguien que
  /// no seas tú hay que poner un dominio propio y añadirlo en Railway.
  ///
  /// Aquí estuvo `https://api.atenea.cl/api/v1`, que **no existe**: `atenea.cl`
  /// está registrado por otra empresa y no hay tal subdominio. Cualquier
  /// compilación de release sin `--dart-define` salía sin servidor, y la
  /// aplicación abría y no cargaba nada. No lo cazó ninguna prueba porque
  /// ninguna sale a la red.
  static const String apiProduccion =
      'https://api-production-66b3.up.railway.app/api/v1';

  /// URL base de la API, incluyendo el prefijo de versión.
  ///
  /// En depuración apunta a la máquina de desarrollo, con la salvedad de que en
  /// el emulador de Android `localhost` es el propio emulador y hay que usar
  /// `10.0.2.2`. En release nunca se apunta a una dirección local: un paquete
  /// publicado que busca el ordenador de quien lo compiló no sirve a nadie.
  static String get apiBase {
    if (_apiDefinida.isNotEmpty) return _apiDefinida;
    if (kReleaseMode) return apiProduccion;
    if (kIsWeb) return 'http://localhost:8000/api/v1';
    return switch (defaultTargetPlatform) {
      TargetPlatform.android => 'http://10.0.2.2:8000/api/v1',
      _ => 'http://localhost:8000/api/v1',
    };
  }

  /// ¿La API a la que se apunta viaja cifrada?
  ///
  /// Solo se consulta para avisar durante el desarrollo. En release, apuntar a
  /// `http://` es además inútil en Android, que bloquea el tráfico en claro.
  static bool get apiEsSegura => apiBase.startsWith('https://');

  /// Esquema de los enlaces profundos que abren la app desde una
  /// notificación: `atenea://home`, `atenea://route/{id}`, etc.
  static const String esquemaEnlaces = 'atenea';

  static bool get esDesarrollo => kDebugMode;
}
