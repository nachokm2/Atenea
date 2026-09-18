/// «Ir a cumplirla» solo aparece cuando hay a dónde ir, y antes no aparecía nunca.
///
/// La hoja de detalle de P19 decide con una línea:
/// `if (destino != null && !mision.estaCumplida)`. `destino` sale de
/// `mision.enlaceProfundo`, que el DTO lee de `deep_link`… y `MissionOut`
/// mandaba diez campos, ninguno de ellos ese. Así que el botón **no se pintó
/// nunca, para ninguna misión**, y en su lugar el aprendiz veía siempre el
/// texto de consolación.
///
/// Es la enfermedad de este proyecto en su forma más limpia: la pantalla carga
/// bien, no falla nada, y le falta la mitad. Ninguna prueba lo notaba porque
/// ninguna miraba este campo.
///
/// Estas pruebas cubren las tres ramas de esa línea, y la tercera es la que
/// impide «arreglarlo» mandando siempre un enlace.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/inicio/misiones.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

/// El sobre tal y como lo manda `MissionOut`.
Map<String, dynamic> _mision({
  String? enlace,
  String estado = 'active',
  String? rutaId,
}) =>
    <String, dynamic>{
      'user_mission_id': 'm-1',
      'template_code': 'S01',
      'scope': 'special',
      'title': 'Termina el módulo 2',
      'target': 2,
      'progress': 1,
      'status': estado,
      'reward': <String, dynamic>{'xp': 120, 'gold': 40},
      'learning_path_id': rutaId,
      'deep_link': enlace,
    };

Future<void> _montar(WidgetTester tester, Map<String, dynamic> sobre) async {
  await tester.binding.setSurfaceSize(const Size(412, 915));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: Scaffold(
        body: DetalleMision(mision: Mision.desdeJson(sobre)),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(prepararTipografias);

  testWidgets('con destino, se ofrece el botón', (WidgetTester tester) async {
    await _montar(tester, _mision(enlace: 'route/abc', rutaId: 'abc'));

    expect(find.text('Ir a cumplirla'), findsOneWidget);
    expect(
      find.textContaining('Avanza en cualquier lección'),
      findsNothing,
      reason: 'con destino no toca el texto de consolación',
    );
  });

  testWidgets('sin destino no se inventa un botón que lleve a cualquier parte',
      (WidgetTester tester) async {
    // Es la rama que impide el arreglo perezoso: mandar siempre un enlace haría
    // que una diaria —«completa dos lecciones», que no tiene un sitio único—
    // ofreciera un botón que lleva a donde sea. Peor que no ofrecerlo.
    await _montar(tester, _mision());

    expect(find.text('Ir a cumplirla'), findsNothing);
    expect(find.textContaining('Avanza en cualquier lección'), findsOneWidget);
  });

  testWidgets('cumplida, tampoco: ya no hay nada que ir a hacer',
      (WidgetTester tester) async {
    await _montar(tester, _mision(enlace: 'route/abc', estado: 'completed'));

    expect(find.text('Ir a cumplirla'), findsNothing);
    expect(find.textContaining('Ya está cumplida'), findsOneWidget);
  });

  testWidgets('el enlace del servidor viaja sin esquema y el cliente lo entiende',
      (WidgetTester tester) async {
    // El servidor manda `route/{id}`, no `atenea://route/{id}`: quien sabe del
    // esquema es el cliente. Si el traductor solo aceptara la forma con
    // esquema, el botón seguiría sin aparecer y el servidor parecería correcto.
    await _montar(tester, _mision(enlace: 'route/abc'));
    expect(find.text('Ir a cumplirla'), findsOneWidget);

    await _montar(tester, _mision(enlace: 'atenea://route/abc'));
    expect(find.text('Ir a cumplirla'), findsOneWidget);
  });

  test('el DTO lee las marcas de tiempo que la hoja pinta', () {
    // `completed_at` alimenta la fila «Cumplida». Tampoco viajaba.
    final Mision m = Mision.desdeJson(<String, dynamic>{
      ..._mision(enlace: 'route/abc'),
      'completed_at': '2026-09-18T10:00:00Z',
      'claimed_at': '2026-09-18T11:00:00Z',
    });

    expect(m.completadaEn, isNotNull);
    expect(m.reclamadaEn, isNotNull);
    expect(m.enlaceProfundo, 'route/abc');
  });
}
