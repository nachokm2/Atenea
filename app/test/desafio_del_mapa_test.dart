/// El desafío del módulo aparece en el mapa de la Ruta.
///
/// El remate de cada módulo —la Prueba del Castillo— estaba escrito entero en
/// el cliente: `ContenidoDesafio` lo dibuja, `_estiloDesafio` decide su aspecto
/// y `_tocarDesafio` lo abre. Pero todo eso cuelga de `modulo.evaluacion`, y
/// ese objeto **nunca llegaba**: el nodo del servidor mandaba
/// `assessment_best_score` y `assessment_passed` sueltos y ningún
/// `assessment`, así que `ModuloRuta.desdeJson` dejaba `evaluacion` en `null`
/// y el nodo simplemente no se pintaba, en ninguna ruta, para nadie.
///
/// Parecía que el dato estaba, porque dos de sus campos sí viajaban. Esa es la
/// razón de que ninguna prueba lo viera: el mapa cargaba sin error y con los
/// módulos correctos; lo que faltaba no daba ningún síntoma.
///
/// Estas pruebas atan el sobre real del servidor —`ModuleAssessmentOut`, §7.5—
/// a lo que el aprendiz ve.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/design/components.dart';
import 'package:atenea/design/theme.dart';
import 'package:atenea/pantallas/aventura/widgets/nodos_mapa.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'ayudas.dart';

/// El objeto `assessment` tal y como lo serializa `ModuleAssessmentOut`.
///
/// Los nombres son los del contrato, no los que le vendrían bien al cliente:
/// si el servidor renombra un campo, esto deja de cuadrar y la prueba cae.
Map<String, dynamic> _desafio({
  int intentosUsados = 0,
  double? mejorPuntaje,
  bool aprobada = false,
  bool puedeEmpezar = true,
  String? enfriamientoHasta,
}) =>
    <String, dynamic>{
      'assessment_id': 'eval-1',
      'module_id': 'mod-1',
      'title': 'Prueba del módulo',
      'question_count': 4,
      'pass_score': 70.0,
      'max_attempts_per_day': 2,
      'content_status': 'ready',
      'attempts_used': intentosUsados,
      'best_score': mejorPuntaje,
      'passed': aprobada,
      'can_start': puedeEmpezar,
      'cooldown_until': enfriamientoHasta,
    };

Map<String, dynamic> _modulo(Map<String, dynamic>? desafio) => <String, dynamic>{
      'module_id': 'mod-1',
      'title': 'Salón de las Puertas',
      'position': 1,
      'status': 'in_progress',
      'content_status': 'ready',
      'lessons_total': 2,
      'lessons_completed': 1,
      'mastery': 40.0,
      'assessment_best_score': null,
      'assessment_passed': false,
      'assessment': desafio,
      'topics': <dynamic>[],
    };

/// Busca una píldora por su texto.
///
/// `find.text` no sirve aquí: `Pildora` pinta con `Text.rich` para poder
/// incrustar el icono en el mismo párrafo, y ese buscador solo mira el `data`
/// de un `Text` llano. Buscar el widget por su campo también deja dicho *qué*
/// se espera —una píldora, no un texto suelto en cualquier parte.
Finder _pildora(String texto) => find.byWidgetPredicate(
      (Widget w) => w is Pildora && w.texto == texto,
      description: 'píldora «$texto»',
    );

Future<void> _montar(
  WidgetTester tester,
  ResumenEvaluacion evaluacion,
  EstiloNodo estilo,
) async {
  await tester.binding.setSurfaceSize(const Size(412, 915));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      theme: AteneaTheme.oscuro(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: ContenidoDesafio(
            evaluacion: evaluacion,
            estilo: estilo,
            alTocar: () {},
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  setUp(prepararTipografias);

  test('el módulo lee el desafío que ahora manda el servidor', () {
    final ModuloRuta modulo = ModuloRuta.desdeJson(
      _modulo(_desafio(intentosUsados: 1, mejorPuntaje: 55)),
    );

    final ResumenEvaluacion? evaluacion = modulo.evaluacion;
    expect(evaluacion, isNotNull, reason: 'sin esto el nodo no se pinta');
    expect(evaluacion!.id, 'eval-1');
    expect(evaluacion.moduloId, 'mod-1');
    expect(evaluacion.preguntas, 4);
    expect(evaluacion.puntajeAprobacion, 70);
    expect(evaluacion.intentosUsados, 1);
    expect(evaluacion.intentosMaximosPorDia, 2);
    expect(evaluacion.mejorPuntaje, 55);
    expect(evaluacion.aprobada, isFalse);
    expect(evaluacion.puedeEmpezar, isTrue);
  });

  test('un módulo sin evaluación deja el desafío en nulo, no en vacío', () {
    // «Sin prueba todavía» y «prueba que no se puede empezar» son estados
    // distintos y se pintan distinto. Un objeto vacío los confundiría.
    expect(ModuloRuta.desdeJson(_modulo(null)).evaluacion, isNull);
  });

  testWidgets('el nodo dice cuántas preguntas, el umbral y la mejor marca',
      (WidgetTester tester) async {
    await _montar(
      tester,
      ResumenEvaluacion.desdeJson(_desafio(mejorPuntaje: 55)),
      EstiloNodo.disponible,
    );

    expect(find.text('Desafío del módulo'), findsOneWidget);
    expect(_pildora('4 preguntas'), findsOneWidget);
    expect(_pildora('Se supera con 70 %'), findsOneWidget);
    expect(_pildora('Tu mejor marca: 55 %'), findsOneWidget);
  });

  testWidgets('sin intentos previos no promete una marca que no existe',
      (WidgetTester tester) async {
    await _montar(
      tester,
      ResumenEvaluacion.desdeJson(_desafio()),
      EstiloNodo.disponible,
    );

    expect(
      find.byWidgetPredicate(
        (Widget w) => w is Pildora && w.texto.contains('Tu mejor marca'),
      ),
      findsNothing,
    );
  });

  testWidgets('el enfriamiento se explica en vez de dejar un botón mudo',
      (WidgetTester tester) async {
    // El fallo que esto evita: `can_start` en falso pinta el nodo bloqueado, y
    // sin este texto el aprendiz ve el desafío apagado sin saber si le falta
    // estudiar o si solo tiene que esperar.
    final String dentroDeCuatroHoras =
        DateTime.now().toUtc().add(const Duration(hours: 4)).toIso8601String();

    await _montar(
      tester,
      ResumenEvaluacion.desdeJson(
        _desafio(
          intentosUsados: 1,
          puedeEmpezar: false,
          enfriamientoHasta: dentroDeCuatroHoras,
        ),
      ),
      EstiloNodo.bloqueado,
    );

    expect(find.textContaining('Vuelve en un rato'), findsOneWidget);
    expect(find.textContaining('Completa las lecciones'), findsNothing);
  });

  testWidgets('bloqueado sin enfriamiento manda a terminar las lecciones',
      (WidgetTester tester) async {
    await _montar(
      tester,
      ResumenEvaluacion.desdeJson(_desafio(puedeEmpezar: false)),
      EstiloNodo.bloqueado,
    );

    expect(find.textContaining('Completa las lecciones'), findsOneWidget);
    expect(find.textContaining('Vuelve en un rato'), findsNothing);
  });

  testWidgets('aprobada se corona con el sello de superado',
      (WidgetTester tester) async {
    await _montar(
      tester,
      ResumenEvaluacion.desdeJson(_desafio(aprobada: true, mejorPuntaje: 90)),
      EstiloNodo.completado,
    );

    expect(find.byIcon(Icons.verified_rounded), findsOneWidget);
    expect(_pildora('Tu mejor marca: 90 %'), findsOneWidget);
  });
}
