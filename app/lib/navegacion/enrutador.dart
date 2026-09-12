/// Enrutador de Atenea.
///
/// Estructura, según §3.2 y §3.3 del documento de experiencia:
///
/// - Un `StatefulShellRoute` con los cuatro destinos de la barra inferior
///   (Inicio, Aventura, Personaje y Perfil) y sus pantallas de lista.
/// - Rutas a pantalla completa, **fuera** del armazón, para los flujos
///   inmersivos: crear ruta, generación, lección y desafío del módulo.
/// - Redirección por estado de sesión: sin sesión se va a la entrada; con
///   sesión pero sin personaje, a la creación de personaje.
/// - Traducción de los enlaces profundos de las notificaciones
///   (`atenea://route/{id}` → `/ruta/{id}`).
/// - Confirmación ligera al abandonar una lección o un desafío a medias.
library;

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../design/components.dart';
import '../design/tokens.dart';
import '../estado/evaluacion.dart';
import '../estado/leccion.dart';
import '../estado/sesion.dart';
import '../pantallas/entrada/acceso.dart';
import '../pantallas/entrada/bienvenida.dart';
import '../pantallas/entrada/crear_personaje.dart';
import '../pantallas/inicio/inicio.dart';
import '../pantallas/inicio/misiones.dart';
import '../pantallas/aventura/aventura.dart';
import '../pantallas/aventura/crear_ruta.dart';
import '../pantallas/aventura/generacion.dart';
import '../pantallas/aventura/mapa_ruta.dart';
import '../pantallas/evaluacion/evaluacion.dart';
import '../pantallas/evaluacion/resultado_evaluacion.dart';
import '../pantallas/leccion/fin_leccion.dart';
import '../pantallas/leccion/leccion.dart';
import '../pantallas/perfil/ajustes.dart';
import '../pantallas/perfil/perfil.dart';
import '../pantallas/perfil/racha.dart';
import '../pantallas/personaje/mercado.dart';
import '../pantallas/personaje/vestidor.dart';
import '../pantallas/perfil/logros.dart';
import '../pantallas/galeria_estilo.dart';
import 'armazon.dart';
import 'rutas.dart';

/// Navegador raíz: sobre él se apilan los flujos inmersivos y las hojas.
final GlobalKey<NavigatorState> llaveNavegadorRaiz =
    GlobalKey<NavigatorState>(debugLabel: 'atenea-raiz');

/// Construye el enrutador con la sesión como fuente de la redirección.
GoRouter crearEnrutador(ControladorSesion sesion) {
  return GoRouter(
    navigatorKey: llaveNavegadorRaiz,
    initialLocation: Rutas.inicio,
    refreshListenable: sesion,
    redirect: (BuildContext context, GoRouterState state) =>
        _redirigir(sesion, state),
    errorBuilder: (BuildContext context, GoRouterState state) =>
        _PantallaPerdida(direccion: state.uri.toString()),
    routes: <RouteBase>[
      // ---------------------------------------------------------------------
      // Entrada: sin barra inferior
      // ---------------------------------------------------------------------
      GoRoute(
        path: Rutas.bienvenida,
        // P01 — splash y onboarding (lib/pantallas/entrada/bienvenida.dart).
        builder: (BuildContext context, GoRouterState state) =>
            const PantallaBienvenida(),
      ),
      GoRoute(
        path: Rutas.acceso,
        // P02 — registro e inicio de sesión
        // (lib/pantallas/entrada/acceso.dart).
        builder: (BuildContext context, GoRouterState state) =>
            const PantallaAcceso(),
      ),
      GoRoute(
        path: Rutas.crearPersonaje,
        // P03 — creación de personaje
        // (lib/pantallas/entrada/crear_personaje.dart).
        builder: (BuildContext context, GoRouterState state) =>
            const PantallaCrearPersonaje(),
      ),

      // ---------------------------------------------------------------------
      // Armazón: los cuatro destinos con barra inferior
      // ---------------------------------------------------------------------
      StatefulShellRoute.indexedStack(
        builder: (
          BuildContext context,
          GoRouterState state,
          StatefulNavigationShell navegacion,
        ) =>
            ArmazonAtenea(navegacion: navegacion),
        branches: <StatefulShellBranch>[
          // --- Inicio --------------------------------------------------
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: Rutas.inicio,
                // P04 · El panel del héroe.
                builder: (BuildContext context, GoRouterState state) =>
                    const PantallaInicio(),
                routes: <RouteBase>[
                  GoRoute(
                    path: Rutas.segMisiones,
                    // P19 · Misiones diarias, semanales y de ruta.
                    builder: (BuildContext context, GoRouterState state) =>
                        const PantallaMisiones(),
                  ),
                ],
              ),
            ],
          ),

          // --- Aventura ------------------------------------------------
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: Rutas.aventura,
                builder: (BuildContext context, GoRouterState state) =>
                    const PantallaAventura(),
              ),
            ],
          ),

          // --- Personaje -----------------------------------------------
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: Rutas.personaje,
                builder: (BuildContext context, GoRouterState state) =>
                    const PantallaVestidor(),
                routes: <RouteBase>[
                  GoRoute(
                    path: Rutas.segMercado,
                    builder: (BuildContext context, GoRouterState state) =>
                        const PantallaMercado(),
                  ),
                ],
              ),
            ],
          ),

          // --- Perfil --------------------------------------------------
          StatefulShellBranch(
            routes: <RouteBase>[
              GoRoute(
                path: Rutas.perfil,
                builder: (BuildContext context, GoRouterState state) =>
                    const PantallaPerfil(),
                routes: <RouteBase>[
                  GoRoute(
                    path: Rutas.segRacha,
                    builder: (BuildContext context, GoRouterState state) =>
                        const PantallaRacha(),
                  ),
                  GoRoute(
                    path: Rutas.segLogros,
                    // P20 · Sala de trofeos.
                    builder: (BuildContext context, GoRouterState state) =>
                        const PantallaLogros(),
                  ),
                  GoRoute(
                    path: Rutas.segAjustes,
                    builder: (BuildContext context, GoRouterState state) =>
                        const PantallaAjustes(),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),

      // ---------------------------------------------------------------------
      // Flujos inmersivos y detalles: pantalla completa, sin barra inferior
      // ---------------------------------------------------------------------
      GoRoute(
        path: Rutas.crearRuta,
        builder: (BuildContext context, GoRouterState state) =>
            const PantallaCrearRuta(),
      ),

      // Galería del sistema de diseño: referencia viva, solo en depuración.
      if (kDebugMode)
        GoRoute(
          path: Rutas.galeriaEstilo,
          builder: (BuildContext context, GoRouterState state) =>
              const PantallaGaleriaEstilo(),
        ),
      GoRoute(
        path: Rutas.patronRuta,
        builder: (BuildContext context, GoRouterState state) => PantallaMapaRuta(
          rutaId: state.pathParameters[Rutas.paramRuta] ?? '',
        ),
        routes: <RouteBase>[
          GoRoute(
            path: Rutas.segGeneracion,
            builder: (BuildContext context, GoRouterState state) =>
                PantallaGeneracion(
              rutaId: state.pathParameters[Rutas.paramRuta] ?? '',
            ),
          ),
        ],
      ),
      GoRoute(
        path: Rutas.patronLeccion,
        onExit: (BuildContext context, GoRouterState state) =>
            confirmarSalidaDeLeccion(context),
        // P08 y P09: el panel de retroalimentación vive dentro de la misma
        // pantalla inmersiva.
        builder: (BuildContext context, GoRouterState state) => PantallaLeccion(
          leccionId: state.pathParameters[Rutas.paramLeccion],
        ),
        routes: <RouteBase>[
          GoRoute(
            path: Rutas.segResumen,
            // P10: desglose del recibo y cola de celebraciones.
            builder: (BuildContext context, GoRouterState state) =>
                PantallaFinLeccion(
              leccionId: state.pathParameters[Rutas.paramLeccion],
            ),
          ),
        ],
      ),
      GoRoute(
        path: Rutas.patronRepaso,
        onExit: (BuildContext context, GoRouterState state) =>
            confirmarSalidaDeLeccion(context),
        // P08 en modo repaso: solo preguntas del tema.
        builder: (BuildContext context, GoRouterState state) => PantallaLeccion(
          temaId: state.pathParameters[Rutas.paramTema],
        ),
      ),
      GoRoute(
        path: Rutas.patronEvaluacion,
        onExit: (BuildContext context, GoRouterState state) =>
            confirmarSalidaDeEvaluacion(context),
        // P11: entrada con reglas y desafío con retroalimentación mínima.
        builder: (BuildContext context, GoRouterState state) =>
            PantallaEvaluacion(
          moduloId: state.pathParameters[Rutas.paramModulo] ?? '',
        ),
        routes: <RouteBase>[
          GoRoute(
            path: Rutas.segResultado,
            // P12: puntaje, desglose por tema y siguiente paso, sin castigo.
            builder: (BuildContext context, GoRouterState state) =>
                PantallaResultadoEvaluacion(
              moduloId: state.pathParameters[Rutas.paramModulo] ?? '',
            ),
          ),
        ],
      ),
    ],
  );
}

/// Redirección: primero traduce enlaces profundos, después aplica el estado
/// de la sesión.
String? _redirigir(ControladorSesion sesion, GoRouterState state) {
  final String? deEnlace = EnlacesProfundos.desdeUri(state.uri);
  if (deEnlace != null && deEnlace != state.matchedLocation) return deEnlace;

  final String destino = state.matchedLocation;
  final bool enEntrada = Rutas.deEntrada.contains(destino);

  switch (sesion.fase) {
    case FaseSesion.arrancando:
      return enEntrada ? null : Rutas.bienvenida;
    case FaseSesion.sinSesion:
      if (enEntrada) return null;
      return sesion.onboardingVisto ? Rutas.acceso : Rutas.bienvenida;
    case FaseSesion.sinPersonaje:
      return destino == Rutas.crearPersonaje ? null : Rutas.crearPersonaje;
    case FaseSesion.lista:
      if (enEntrada || destino == Rutas.crearPersonaje) return Rutas.inicio;
      return null;
  }
}

/// Confirmación ligera al salir de una lección a medias (§3.3 regla 2).
///
/// Devuelve `true` si se puede salir. El avance del paso ya está guardado en
/// el servidor gracias a los latidos, por eso el mensaje tranquiliza en vez
/// de advertir.
Future<bool> confirmarSalidaDeLeccion(BuildContext context) async {
  final ControladorLeccion leccion = context.read<ControladorLeccion>();
  if (!leccion.enProgreso) return true;
  final bool salir = await _preguntar(
    context,
    titulo: '¿Dejamos la lección aquí?',
    mensaje:
        'Guardamos tu avance en este paso. Puedes retomarla cuando quieras.',
    textoSalir: 'Salir',
    textoQuedarse: 'Seguir aquí',
  );
  if (!salir) return false;
  await leccion.abandonar();
  return true;
}

/// Confirmación al salir del Desafío del módulo (se pierde el intento, no el
/// progreso del módulo).
Future<bool> confirmarSalidaDeEvaluacion(BuildContext context) async {
  final ControladorEvaluacion evaluacion = context.read<ControladorEvaluacion>();
  if (!evaluacion.enProgreso) return true;
  final bool salir = await _preguntar(
    context,
    titulo: '¿Abandonas el desafío?',
    mensaje:
        'Se pierde este intento, pero no tu progreso en el módulo. Podrás '
        'volver a intentarlo con preguntas distintas.',
    textoSalir: 'Abandonar',
    textoQuedarse: 'Seguir el desafío',
  );
  if (!salir) return false;
  evaluacion.abandonar();
  return true;
}

Future<bool> _preguntar(
  BuildContext context, {
  required String titulo,
  required String mensaje,
  required String textoSalir,
  required String textoQuedarse,
}) async {
  final AteneaPalette paleta = context.paleta;
  final bool? respuesta = await showDialog<bool>(
    context: context,
    builder: (BuildContext dialogo) => AlertDialog(
      backgroundColor: paleta.superficieElevada,
      shape: const RoundedRectangleBorder(borderRadius: Redondeo.rTarjeta),
      title: Text(titulo),
      content: Text(mensaje),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(dialogo).pop(false),
          child: Text(textoQuedarse),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogo).pop(true),
          child: Text(textoSalir),
        ),
      ],
    ),
  );
  return respuesta ?? false;
}

/// Dirección desconocida: nunca se muestra un código técnico.
class _PantallaPerdida extends StatelessWidget {
  const _PantallaPerdida({required this.direccion});

  final String direccion;

  @override
  Widget build(BuildContext context) {
    return PantallaAtenea(
      titulo: 'Camino sin mapa',
      cuerpo: EstadoVacio(
        icono: Icons.explore_off_rounded,
        titulo: 'Este sendero no existe',
        mensaje:
            'No encontramos esa parte del Reino. Volvamos a un lugar conocido.',
        textoAccion: 'Ir al Inicio',
        alTocarAccion: () => context.go(Rutas.inicio),
      ),
    );
  }
}
