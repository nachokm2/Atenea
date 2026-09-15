import 'package:atenea/datos/dtos.dart';
import 'package:atenea/navegacion/rutas.dart';
import 'package:flutter_test/flutter_test.dart';

/// Tres desajustes entre lo que el servidor manda y lo que el cliente leía.
///
/// Ninguno daba error: el cliente enseñaba un valor por defecto y seguía tan
/// tranquilo. Por eso conviene fijarlos aquí, donde una regresión se ve, y no
/// esperar a que alguien mire una pantalla y note que todos los repasos duran
/// exactamente cinco minutos.
void main() {
  group('duración del repaso', () {
    test('lee los segundos que manda ReviewSuggestionOut', () {
      final SugerenciaRepaso s = SugerenciaRepaso.desdeJson(<String, dynamic>{
        'topic_id': 'tema-1',
        'title': 'JOINs',
        'estimated_seconds': 480,
      });

      expect(s.minutosEstimados, 8);
    });

    test('redondea hacia arriba: minuto y medio son dos minutos', () {
      final SugerenciaRepaso s = SugerenciaRepaso.desdeJson(<String, dynamic>{
        'topic_id': 'tema-1',
        'title': 'JOINs',
        'estimated_seconds': 90,
      });

      expect(s.minutosEstimados, 2);
    });

    test('sin duración se queda en la estimación de cortesía', () {
      final SugerenciaRepaso s = SugerenciaRepaso.desdeJson(<String, dynamic>{
        'topic_id': 'tema-1',
        'title': 'JOINs',
        'reason': 'assessment_weak_topic',
      });

      expect(s.minutosEstimados, 5);
    });
  });

  group('bandeja de avisos', () {
    test('un aviso sin envío todavía enseña cuándo se creó', () {
      final Notificacion n = Notificacion.desdeJson(<String, dynamic>{
        'id': 'aviso-1',
        'notification_type': 'streak_reminder',
        'status': 'pending',
        'title': 'Tu racha sigue en pie',
        'body': 'Un rato basta.',
        'created_at': '2026-03-10T22:00:00Z',
      });

      expect(n.fechaVisible, isNotNull);
      expect(n.fechaVisible!.toUtc().hour, 22);
    });

    test('el envío manda sobre la creación', () {
      final Notificacion n = Notificacion.desdeJson(<String, dynamic>{
        'id': 'aviso-2',
        'notification_type': 'review_recommended',
        'status': 'sent',
        'title': 'Un repaso corto',
        'body': 'Cuatro preguntas.',
        'sent_at': '2026-03-11T12:00:00Z',
        'created_at': '2026-03-10T22:00:00Z',
      });

      expect(n.fechaVisible!.toUtc().day, 11);
    });

    test('los enlaces que escribe el servidor llevan a alguna parte', () {
      // Son los cuatro que crea el backend hoy. Un enlace que el traductor no
      // entienda acaba en Inicio sin decir por qué, así que más vale fijarlos.
      expect(EnlacesProfundos.aDireccionInterna('streak'), Rutas.racha);
      expect(EnlacesProfundos.aDireccionInterna('missions'), Rutas.misiones);
      expect(EnlacesProfundos.aDireccionInterna('home'), Rutas.inicio);
      expect(
        EnlacesProfundos.aDireccionInterna('review/tema-7'),
        Rutas.repaso('tema-7'),
      );
      expect(
        EnlacesProfundos.aDireccionInterna('route/ruta-3'),
        Rutas.ruta('ruta-3'),
      );
      expect(
        EnlacesProfundos.aDireccionInterna('route/ruta-3/generation'),
        Rutas.generacion('ruta-3'),
      );
    });
  });

  group('tarjeta de continuar', () {
    test('un repaso trae el tema al que hay que ir', () {
      final AccionContinuar a = AccionContinuar.desdeJson(<String, dynamic>{
        'type': 'review',
        'topic_id': 'tema-9',
        'title': 'JOINs',
        'breadcrumb': 'Dominar SQL · Consultas',
        'reward_preview': <String, dynamic>{'xp': 30, 'gold': 8},
      });

      expect(a.tipo, TipoAccionContinuar.repaso);
      expect(a.temaId, 'tema-9');
      expect(Rutas.repaso(a.temaId!), '/repaso/tema-9');
    });
  });

  group('panel', () {
    test('la campana lee el contador que ahora manda el panel', () {
      final Panel p = Panel.desdeJson(<String, dynamic>{
        'greeting_key': 'buenas_tardes',
        'unread_notifications': 3,
      });

      expect(p.notificacionesSinLeer, 3);
    });
  });
}
