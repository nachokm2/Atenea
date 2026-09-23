/// Mapa de rutas de la aplicación y traductor de enlaces profundos.
///
/// Una sola fuente de verdad para las direcciones internas: las pantallas
/// navegan con estas constantes, nunca con cadenas escritas a mano.
///
/// Los enlaces profundos que envían las notificaciones usan los nombres en
/// inglés del documento de UX (§3.3 regla 6) —`atenea://route/{id}`— y aquí
/// se traducen a la dirección interna en español.
library;

import '../nucleo/entorno.dart';

/// Direcciones internas de la aplicación.
abstract final class Rutas {
  // --- Flujo de entrada (sin barra inferior) -------------------------------

  /// P01 · Splash y onboarding.
  static const String bienvenida = '/bienvenida';

  /// P02 · Registro y acceso.
  static const String acceso = '/acceso';

  /// P02b · Elegir contraseña nueva con el enlace del correo.
  ///
  /// Es también el destino del enlace profundo `atenea://password/reset`, que es
  /// lo que se envía por correo al pedir la recuperación.
  static const String nuevaContrasena = '/nueva-contrasena';

  /// P03 · Creación de personaje.
  static const String crearPersonaje = '/crear-personaje';

  // --- Destinos raíz (con barra inferior) ----------------------------------

  /// P04 · Inicio.
  static const String inicio = '/inicio';

  /// P19 · Misiones, colgada de Inicio.
  static const String misiones = '/inicio/misiones';

  /// Repasos recomendados, colgada de Inicio: temas en riesgo o débiles.
  static const String repasosRecomendados = '/inicio/repasos';

  /// P22 · Aventura: mis territorios y Rutas del Reino.
  static const String aventura = '/aventura';

  /// P16 · Vestidor.
  static const String personaje = '/personaje';

  /// P15 · Mercado, colgado de Personaje.
  static const String mercado = '/personaje/mercado';

  /// Monedero: saldo, oro de por vida y el historial de movimientos.
  static const String monedero = '/personaje/monedero';

  /// P17 · Perfil.
  static const String perfil = '/perfil';

  /// P18 · Racha y calendario.
  static const String racha = '/perfil/racha';

  /// P20 · Logros.
  static const String logros = '/perfil/logros';

  /// P21 · Ajustes.
  static const String ajustes = '/perfil/ajustes';

  /// Galería del sistema de diseño. Solo existe en compilaciones de
  /// depuración; Ajustes la enlaza bajo "Herramientas del Reino".
  static const String galeriaEstilo = '/galeria-estilo';

  /// Spike descartable de la Fase 0 (mundo caminable de P07). Solo existe en
  /// compilaciones de depuración; se borra entero si el experimento no
  /// convence. Ver `docs/planes` (Fase 0).
  static const String experimentoMundo = '/experimento-mundo';

  // --- Flujos inmersivos y detalles (sin barra inferior) -------------------

  /// P05 · Crear ruta.
  static const String crearRuta = '/crear-ruta';

  /// P07 · Mapa de una ruta.
  static String ruta(String rutaId) => '/ruta/$rutaId';

  /// P06 · Estado de la generación de una ruta.
  static String generacion(String rutaId) => '/ruta/$rutaId/generacion';

  /// P08 y P09 · Lección y sus preguntas.
  static String leccion(String leccionId) => '/leccion/$leccionId';

  /// P10 · Fin de lección.
  static String finLeccion(String leccionId) => '/leccion/$leccionId/resumen';

  /// Lección en modo repaso de un tema.
  static String repaso(String temaId) => '/repaso/$temaId';

  /// Reto opcional de un módulo ya completado.
  static String reto(String moduloId) => '/reto/$moduloId';

  /// P11 · Desafío del módulo.
  static String evaluacion(String moduloId) => '/evaluacion/$moduloId';

  /// P12 · Resultado del desafío.
  static String resultadoEvaluacion(String moduloId) =>
      '/evaluacion/$moduloId/resultado';

  // --- Segmentos relativos, para declarar las rutas hijas ------------------

  /// Segmento de P19 bajo Inicio.
  static const String segMisiones = 'misiones';

  /// Segmento de repasos recomendados bajo Inicio.
  static const String segRepasosRecomendados = 'repasos';

  /// Segmento de P15 bajo Personaje.
  static const String segMercado = 'mercado';

  /// Segmento del Monedero bajo Personaje.
  static const String segMonedero = 'monedero';

  /// Segmento de P18 bajo Perfil.
  static const String segRacha = 'racha';

  /// Segmento de P20 bajo Perfil.
  static const String segLogros = 'logros';

  /// Segmento de P21 bajo Perfil.
  static const String segAjustes = 'ajustes';

  /// Segmento de P06 bajo el mapa de la ruta.
  static const String segGeneracion = 'generacion';

  /// Segmento de P10 bajo la lección.
  static const String segResumen = 'resumen';

  /// Segmento de P12 bajo el desafío.
  static const String segResultado = 'resultado';

  // --- Patrones con parámetros ---------------------------------------------

  /// Patrón de P07.
  static const String patronRuta = '/ruta/:$paramRuta';

  /// Patrón de P08.
  static const String patronLeccion = '/leccion/:$paramLeccion';

  /// Patrón del repaso de un tema.
  static const String patronRepaso = '/repaso/:$paramTema';

  /// Patrón del Reto de un módulo.
  static const String patronReto = '/reto/:$paramModulo';

  /// Patrón de P11.
  static const String patronEvaluacion = '/evaluacion/:$paramModulo';

  /// Nombre del parámetro de ruta.
  static const String paramRuta = 'rutaId';

  /// Nombre del parámetro de lección.
  static const String paramLeccion = 'leccionId';

  /// Nombre del parámetro de tema.
  static const String paramTema = 'temaId';

  /// Nombre del parámetro de módulo.
  static const String paramModulo = 'moduloId';

  /// Los cuatro destinos de la barra inferior, en su orden visual.
  static const List<String> destinosRaiz = <String>[
    inicio,
    aventura,
    personaje,
    perfil,
  ];

  /// Direcciones que forman el flujo de entrada (antes de tener sesión).
  static const List<String> deEntrada = <String>[
    bienvenida,
    acceso,
    // El enlace del correo llega casi siempre sin sesión, que es justo el caso:
    // se abre porque no se puede entrar.
    nuevaContrasena,
  ];

  /// Índice del destino de la barra al que pertenece una dirección.
  /// Devuelve `0` (Inicio) cuando no pertenece a ninguno.
  static int indiceDeDestino(String direccion) {
    for (int i = destinosRaiz.length - 1; i >= 0; i--) {
      if (direccion == destinosRaiz[i] ||
          direccion.startsWith('${destinosRaiz[i]}/')) {
        return i;
      }
    }
    return 0;
  }
}

/// Enlaces profundos que abren la aplicación desde una notificación.
abstract final class EnlacesProfundos {
  /// Esquema propio: `atenea://…`.
  static const String esquema = Entorno.esquemaEnlaces;

  /// `atenea://home`
  static const String inicio = '$esquema://home';

  /// `atenea://missions`
  static const String misiones = '$esquema://missions';

  /// `atenea://streak`
  static const String racha = '$esquema://streak';

  /// `atenea://shop`
  static const String mercado = '$esquema://shop';

  /// `atenea://profile`
  static const String perfil = '$esquema://profile';

  /// `atenea://route/{id}`
  static String ruta(String rutaId) => '$esquema://route/$rutaId';

  /// `atenea://route/{id}/generation`
  static String generacion(String rutaId) =>
      '$esquema://route/$rutaId/generation';

  /// `atenea://lesson/{id}`
  static String leccion(String leccionId) => '$esquema://lesson/$leccionId';

  /// `atenea://password/reset?token=…`, el enlace del correo de recuperación.
  static const String nuevaContrasena = '$esquema://password/reset';

  /// Traduce un enlace profundo a una dirección interna.
  ///
  /// Acepta tanto la forma con esquema (`atenea://route/abc`) como la forma
  /// de ruta suelta que envían algunas cargas de notificación (`/route/abc`).
  /// Devuelve `null` cuando el enlace no corresponde a ningún destino
  /// conocido — por ejemplo, porque ya es una dirección interna.
  static String? aDireccionInterna(String? enlace) {
    if (enlace == null || enlace.isEmpty) return null;
    final Uri? uri = Uri.tryParse(enlace);
    if (uri == null) return null;
    return _traducir(uri);
  }

  /// Igual que [aDireccionInterna], pero partiendo de un [Uri] ya analizado.
  static String? desdeUri(Uri uri) => _traducir(uri);

  static String? _traducir(Uri uri) {
    final List<String> partes = <String>[
      if (uri.scheme == esquema && uri.host.isNotEmpty) uri.host,
      ...uri.pathSegments.where((String s) => s.isNotEmpty),
    ];
    if (partes.isEmpty) return null;

    switch (partes.first) {
      case 'home':
        return Rutas.inicio;
      case 'missions':
        return Rutas.misiones;
      case 'streak':
        return Rutas.racha;
      case 'shop':
        return Rutas.mercado;
      case 'profile':
        return Rutas.perfil;
      case 'achievements':
        return Rutas.logros;
      case 'settings':
        return Rutas.ajustes;
      case 'character':
        return Rutas.personaje;
      case 'paths':
        return Rutas.aventura;
      case 'route':
      case 'path':
        if (partes.length < 2) return Rutas.aventura;
        final String rutaId = partes[1];
        if (partes.length >= 3 && partes[2] == 'generation') {
          return Rutas.generacion(rutaId);
        }
        return Rutas.ruta(rutaId);
      case 'password':
        // El permiso viaja en la consulta y tiene que sobrevivir a la
        // traducción: sin él la pantalla no puede hacer nada.
        if (partes.length < 2 || partes[1] != 'reset') return null;
        final String permiso = uri.queryParameters['token'] ?? '';
        return permiso.isEmpty
            ? Rutas.nuevaContrasena
            : '${Rutas.nuevaContrasena}?token=${Uri.encodeQueryComponent(permiso)}';
      case 'lesson':
        if (partes.length < 2) return null;
        return Rutas.leccion(partes[1]);
      case 'review':
        if (partes.length < 2) return null;
        return Rutas.repaso(partes[1]);
      case 'assessment':
        if (partes.length < 2) return null;
        return Rutas.evaluacion(partes[1]);
      default:
        return null;
    }
  }
}
