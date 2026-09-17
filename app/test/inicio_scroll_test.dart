/// Inicio no debe dejar un vacío al final del desplazamiento.
///
/// Rodrigo lo vio usando la aplicación en su móvil: la pantalla sigue
/// desplazándose bastante después de que el contenido se acabe. Ninguna prueba
/// lo miraba, porque todas comprueban que las cosas se pinten y ninguna cuánto
/// se puede desplazar.
///
/// Lo que se mide es la diferencia entre el alto del contenido y el de la
/// ventana. Un poco de margen al final es deliberado —el aire que separa la
/// última fila de la barra inferior—, pero un vacío de media pantalla no.
library;

import 'package:atenea/datos/repositorios.dart';
import 'package:atenea/estado/gamificacion.dart';
import 'package:atenea/estado/panel.dart';
import 'package:atenea/estado/sesion.dart';
import 'package:atenea/pantallas/inicio/inicio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'ayudas.dart';

/// Un panel de verdad, con el JSON que devuelve el Reino.
final Map<String, dynamic> _panelJson = <String, dynamic>{
  'greeting_key': 'morning',
  'character': <String, dynamic>{
    'character_id': '11111111-1111-1111-1111-111111111111',
    'name': 'Rodrigo',
    'archetype': 'steel',
    'level': 4,
    'xp_total': 520,
    'xp_into_level': 20,
    'xp_for_next': 200,
    'rank_title': 'Escudero',
  },
  'streak': <String, dynamic>{
    'current': 3,
    'best': 7,
    'status': 'active',
    'day_status': 'active',
    'total_active_days': 9,
    'grace_available': true,
  },
  'gold_balance': 120,
  'daily_goal': <String, dynamic>{
    'type': 'minutes',
    'target': 20,
    'progress': 8,
    'met': false,
    'effective_from': '2026-09-17',
  },
  'continue_action': <String, dynamic>{
    'type': 'lesson',
    'title': 'Uniones internas',
    'lesson_id': '22222222-2222-2222-2222-222222222222',
    'path_id': '33333333-3333-3333-3333-333333333333',
  },
  'knowledge_areas': <Map<String, dynamic>>[
    <String, dynamic>{
      'knowledge_area_id': '44444444-4444-4444-4444-444444444444',
      'name': 'SQL',
      'short_name': 'SQL',
      'mastery': 0.42,
      'level': 2,
    },
  ],
  'week_stats': <String, dynamic>{
    'minutes': 95,
    'activities': 12,
    'educational_xp': 340,
    'active_days': 3,
  },
  'unread_notifications': 2,
};

/// Panel fijo: la pantalla no debe pedir nada a la red.
class _PanelDePrueba extends ControladorPanel {
  _PanelDePrueba(super.repos, this._fijo);

  final Panel _fijo;

  @override
  Panel? get panel => _fijo;

  @override
  bool get hayDatos => true;

  @override
  bool get errorSinDatos => false;

  @override
  Future<void> cargar({bool forzar = false}) async {}

  @override
  Future<void> refrescar() async {}
}

void main() {
  setUp(prepararTipografias);

  testWidgets('el desplazamiento de Inicio acaba donde acaba el contenido',
      (WidgetTester tester) async {
    // Un móvil corriente.
    await tester.binding.setSurfaceSize(const Size(412, 915));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final AlmacenTokensFalso tokens = AlmacenTokensFalso();
    final Repositorios repos = repositoriosDePrueba(tokens);
    final Panel fijo = Panel.desdeJson(_panelJson);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          Provider<Repositorios>.value(value: repos),
          ChangeNotifierProvider<ControladorSesion>(
            create: (_) => ControladorSesion(repositorios: repos, tokens: tokens),
          ),
          ChangeNotifierProvider<ControladorPanel>(
            create: (_) => _PanelDePrueba(repos, fijo),
          ),
          ChangeNotifierProvider<ControladorGamificacion>(
            create: (_) => ControladorGamificacion(repos),
          ),
        ],
        // Con el armazon de verdad: la aplicacion mete el Scaffold de la
        // pantalla DENTRO de otro Scaffold que lleva la barra inferior.
        child: MaterialApp(
          home: Scaffold(
            body: const PantallaInicio(),
            bottomNavigationBar: NavigationBar(
              destinations: const <Widget>[
                NavigationDestination(icon: Icon(Icons.home), label: 'Inicio'),
                NavigationDestination(icon: Icon(Icons.map), label: 'Aventura'),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 600));

    final ScrollableState desplazable = tester.state(find.byType(Scrollable));
    final ScrollPosition posicion = desplazable.position;

    // `maxScrollExtent` es cuánto se puede desplazar más allá de la ventana.
    // Con el contenido que cabe en dos pantallas largas, pasar de una pantalla
    // entera de sobra significa que hay un vacío, no un margen.
    // Hasta el final del todo, que es donde Rodrigo vio el vacio.
    await tester.drag(find.byType(Scrollable), const Offset(0, -4000));
    await tester.pumpAndSettle();

    // El ultimo pixel que alguien pinta, sea quien sea.
    double masAbajo = 0;
    void medir(Element elemento) {
      final RenderObject? render = elemento.renderObject;
      if (render is RenderBox && render.hasSize && render.attached) {
        final double abajo = render.localToGlobal(Offset(0, render.size.height)).dy;
        if (render.size.height > 0 && abajo > masAbajo) masAbajo = abajo;
      }
      elemento.visitChildren(medir);
    }
    tester.element(find.byType(Scrollable)).visitChildren(medir);

    final double ventana = posicion.viewportDimension;
    final double vacio = ventana - masAbajo;

    // Un respiro al final es deliberado; media pantalla en blanco no lo es.
    expect(
      vacio,
      lessThan(120),
      reason: 'quedan ${vacio.round()} px en blanco despues del contenido, '
          'en una ventana de ${ventana.round()}',
    );

    // Y la comprobacion directa: la altura infinita salta como asercion de
    // maquetacion. En depuracion se ve; en release, que es donde vive la
    // aplicacion, no hay asercion y el fallo solo se nota desplazandose.
    expect(
      tester.takeException(),
      isNull,
      reason: 'algo en Inicio se maqueta con altura infinita',
    );
  });
}
