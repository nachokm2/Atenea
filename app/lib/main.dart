/// Arranque de Atenea.
///
/// Orden del encendido:
///
/// 1. Almacén de tokens y [ApiClient], con el aviso de sesión perdida ya
///    conectado al [ControladorSesion].
/// 2. [Repositorios] sobre ese cliente: una sola instancia para toda la app.
/// 3. Controladores de estado, registrados en un `MultiProvider`.
/// 4. Carga inicial (preferencia de tema y `/auth/me`) antes de pintar, para
///    que el enrutador ya sepa a dónde llevar al usuario.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'data/almacen_tokens.dart';
import 'data/api_client.dart';
import 'datos/repositorios.dart';
import 'estado/aventura.dart';
import 'estado/celebraciones.dart';
import 'estado/evaluacion.dart';
import 'estado/gamificacion.dart';
import 'estado/leccion.dart';
import 'estado/panel.dart';
import 'estado/personaje.dart';
import 'estado/sesion.dart';
import 'navegacion/enrutador.dart';
import 'nucleo/controlador_tema.dart';
import 'nucleo/entorno.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final AlmacenTokens tokens = AlmacenTokens();

  // El cliente necesita avisar al controlador de sesión, y el controlador
  // necesita al cliente: se rompe el círculo con una referencia diferida que
  // queda resuelta antes de la primera petición.
  ControladorSesion? sesionViva;
  final ApiClient cliente = ApiClient(
    baseUrl: Entorno.apiBase,
    tokens: tokens,
    alPerderSesion: () => sesionViva?.alPerderSesion(),
  );

  final Repositorios repositorios = Repositorios(cliente);

  final ControladorSesion sesion = ControladorSesion(
    repositorios: repositorios,
    tokens: tokens,
  );
  sesionViva = sesion;

  final ControladorTema tema = ControladorTema();
  final ControladorPanel panel = ControladorPanel(repositorios);
  final ControladorAventura aventura = ControladorAventura(repositorios);
  final ControladorLeccion leccion = ControladorLeccion(repositorios);
  final ControladorEvaluacion evaluacion = ControladorEvaluacion(repositorios);
  final ControladorPersonaje personaje = ControladorPersonaje(repositorios);
  final ControladorGamificacion gamificacion =
      ControladorGamificacion(repositorios);
  final ColaCelebraciones celebraciones = ColaCelebraciones();

  // Al cerrar sesión (o al perderla) nadie debe conservar datos del héroe
  // anterior.
  bool habiaSesion = false;
  sesion.addListener(() {
    final bool hay = sesion.haySesion;
    if (habiaSesion && !hay) {
      panel.limpiar();
      aventura.limpiar();
      leccion.cerrar();
      evaluacion.cerrar();
      personaje.limpiar();
      gamificacion.limpiar();
      celebraciones.vaciar();
    }
    habiaSesion = hay;
  });

  await Future.wait<void>(<Future<void>>[
    tema.cargar(),
    sesion.arrancar(),
  ]);

  final GoRouter enrutador = crearEnrutador(sesion);

  runApp(
    MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: cliente),
        Provider<Repositorios>.value(value: repositorios),
        ChangeNotifierProvider<ControladorSesion>.value(value: sesion),
        ChangeNotifierProvider<ControladorTema>.value(value: tema),
        ChangeNotifierProvider<ControladorPanel>.value(value: panel),
        ChangeNotifierProvider<ControladorAventura>.value(value: aventura),
        ChangeNotifierProvider<ControladorLeccion>.value(value: leccion),
        ChangeNotifierProvider<ControladorEvaluacion>.value(value: evaluacion),
        ChangeNotifierProvider<ControladorPersonaje>.value(value: personaje),
        ChangeNotifierProvider<ControladorGamificacion>.value(
          value: gamificacion,
        ),
        ChangeNotifierProvider<ColaCelebraciones>.value(value: celebraciones),
      ],
      child: AplicacionAtenea(enrutador: enrutador),
    ),
  );
}
