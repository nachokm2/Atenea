/// P11 no podía distinguir «intentos de hoy» de «intentos de siempre».
///
/// `UserModuleProgress.assessment_attempts` es el histórico real —se
/// actualiza en cada intento cerrado, sobrevive a que el banco se
/// regenere— y ningún endpoint lo exponía (tercer rastreo, 22-09).
/// `AssessmentInfoOut` ahora manda `assessment_attempts` junto a
/// `attempts_used` (el de hoy); esta prueba comprueba que el cliente lee el
/// campo correcto en el campo correcto, sin confundir uno con el otro.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:flutter_test/flutter_test.dart';

/// Copiado de `AssessmentInfoOut` campo a campo, con los nombres del servidor.
Map<String, dynamic> _sobreDelReino({
  int intentosUsados = 1,
  int intentosDePorVida = 4,
}) =>
    <String, dynamic>{
      'assessment': <String, dynamic>{
        'assessment_id': '3f2a1c44-0000-4000-8000-000000000010',
        'module_id': '3f2a1c44-0000-4000-8000-000000000011',
        'title': 'Prueba del módulo',
        'question_count': 10,
        'pass_score': 70.0,
        'max_attempts_per_day': 2,
        'content_status': 'ready',
      },
      'module_title': 'Consultas',
      'attempts_used': intentosUsados,
      'attempts_total': intentosUsados,
      'cooldown_until': null,
      'can_start': true,
      'best_score': null,
      'reward_preview': <String, dynamic>{'xp': 300, 'gold': 100},
      'topic_titles': <String>['JOINs'],
      'assessment_attempts': intentosDePorVida,
    };

void main() {
  test('el histórico de por vida llega en su propio campo', () {
    final InfoEvaluacion info = InfoEvaluacion.desdeJson(
      _sobreDelReino(intentosUsados: 1, intentosDePorVida: 4),
    );

    expect(info.intentosDePorVida, 4);
  });

  test('no se confunde con los intentos de hoy, aunque coincidan', () {
    final InfoEvaluacion info = InfoEvaluacion.desdeJson(
      _sobreDelReino(intentosUsados: 1, intentosDePorVida: 1),
    );

    expect(info.intentosUsados, 1);
    expect(info.intentosDePorVida, 1);
  });

  test('sin el campo (sobre viejo), no inventa un histórico', () {
    final Map<String, dynamic> sobre = _sobreDelReino()
      ..remove('assessment_attempts');

    final InfoEvaluacion info = InfoEvaluacion.desdeJson(sobre);

    expect(info.intentosDePorVida, 0);
  });
}
