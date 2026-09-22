/// `GET /me/knowledge` estaba huérfano y su DTO, además, desalineado.
///
/// El cliente tenía un `ConocimientoUsuario` entero leyendo
/// `topics_total`/`modules_completed`/`active_paths`/`first_activity_at`/
/// `decay_applied` — ninguno de los cuales existe en el `UserKnowledgeOut`
/// real (que manda `topics_mastered`/`modules_total`/`modules_mastered`/
/// `paths_completed`/`last_activity_at`). Y nadie lo iba a notar nunca: el
/// endpoint no lo llamaba ninguna pantalla.
///
/// El arreglo barato (tercer rastreo, 22-09): esos mismos datos ya viajan en
/// `GET /profile` → `knowledge[]`, que P17 ya pide, con la forma exacta de
/// `UserKnowledgeOut`. Bastaba con que `AreaConocimiento.desdeJson` —la
/// clase que P17 sí usa— leyera los cuatro campos que le faltaban, en vez de
/// cablear el endpoint aparte. `ConocimientoUsuario` y `miConocimiento()` se
/// borraron: no tenían un solo llamador y quedaban desincronizados del
/// contrato en cuanto este cambiara.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:flutter_test/flutter_test.dart';

/// Copiado de `UserKnowledgeOut` campo a campo, con los nombres del servidor.
Map<String, dynamic> _filaDelReino() => <String, dynamic>{
      'knowledge_area_id': '3f2a1c44-0000-4000-8000-000000000003',
      'slug': 'sql',
      'name': 'SQL y Bases de Datos',
      'short_name': 'SQL',
      'icon_key': 'castle',
      'accent_color': '#4A90D9',
      'xp': 3200,
      'level': 7,
      'rank_title': 'Competente en',
      'mastery': 68.5,
      'study_seconds': 5400,
      'modules_total': 6,
      'modules_mastered': 4,
      'topics_mastered': 11,
      'paths_completed': 1,
      'status': 'in_progress',
      'last_activity_at': '2026-09-20T18:30:00Z',
    };

void main() {
  test('los cuatro campos que faltaban llegan con sus nombres reales', () {
    final AreaConocimiento a = AreaConocimiento.desdeJson(_filaDelReino());

    expect(a.modulosTotales, 6);
    expect(a.modulosDominados, 4);
    expect(a.temasDominados, 11);
    expect(a.rutasCompletadas, 1);
  });

  test('el resto del sobre sigue llegando como antes', () {
    final AreaConocimiento a = AreaConocimiento.desdeJson(_filaDelReino());

    expect(a.nombre, 'SQL y Bases de Datos');
    expect(a.nivel, 7);
    expect(a.dominio, 68.5);
    expect(a.ultimaActividadEn, isNotNull);
  });

  test('sin esos campos (sobre viejo), no inventa progreso', () {
    final Map<String, dynamic> sobre = _filaDelReino()
      ..remove('modules_total')
      ..remove('modules_mastered')
      ..remove('topics_mastered')
      ..remove('paths_completed');

    final AreaConocimiento a = AreaConocimiento.desdeJson(sobre);

    expect(a.modulosTotales, 0);
    expect(a.modulosDominados, 0);
    expect(a.temasDominados, 0);
    expect(a.rutasCompletadas, 0);
  });
}
