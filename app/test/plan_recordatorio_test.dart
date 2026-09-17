/// El recordatorio local suena a la hora que debe, y no a deshora.
///
/// Esta es la parte del recordatorio que se puede equivocar sin que nadie lo
/// note: el aviso salta, pero a las tres de la madrugada, o el día equivocado, o
/// a quien ya estudió. No hay pantalla roja ni excepción; solo un aprendiz que
/// desactiva los avisos a la semana y nunca dice por qué.
///
/// Las reglas son las del servidor —`en_silencio` y `fuera_del_silencio` en
/// `backend/app/modules/gamification/avisos.py`—, así que los casos de aquí son
/// los que ese archivo documenta en sus propios comentarios. Si algún día las
/// dos mitades divergen, estas pruebas son el único sitio donde se va a notar.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/nucleo/plan_recordatorio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  /// La franja de silencio de fábrica: cruza la medianoche.
  const HoraLocal noche = HoraLocal(22, 0);
  const HoraLocal manana = HoraLocal(8, 0);

  DateTime elMartes(int hora, [int minuto = 0]) =>
      DateTime(2026, 9, 15, hora, minuto);

  group('en silencio', () {
    test('la franja que cruza la medianoche cubre las dos mitades', () {
      // Antes de medianoche.
      expect(enSilencio(const HoraLocal(23, 30), noche, manana), isTrue);
      // Después.
      expect(enSilencio(const HoraLocal(3, 0), noche, manana), isTrue);
      // El borde de entrada cuenta; el de salida no.
      expect(enSilencio(noche, noche, manana), isTrue);
      expect(enSilencio(manana, noche, manana), isFalse);
      // Pleno día.
      expect(enSilencio(const HoraLocal(19, 0), noche, manana), isFalse);
    });

    test('la franja que no cruza se lee como un intervalo normal', () {
      const HoraLocal desde = HoraLocal(13, 0);
      const HoraLocal hasta = HoraLocal(16, 0);
      expect(enSilencio(const HoraLocal(14, 0), desde, hasta), isTrue);
      expect(enSilencio(const HoraLocal(12, 59), desde, hasta), isFalse);
      expect(enSilencio(hasta, desde, hasta), isFalse);
    });

    test('inicio igual que fin es «sin silencio», no silencio de 24 horas', () {
      // La otra lectura dejaría al aprendiz sin un solo aviso sin haberlo
      // pedido. `PUT /settings` admite ese valor, así que llega de verdad.
      const HoraLocal misma = HoraLocal(9, 0);
      expect(enSilencio(const HoraLocal(3, 0), misma, misma), isFalse);
      expect(enSilencio(misma, misma, misma), isFalse);
    });

    test('sin franja configurada, nunca hay silencio', () {
      expect(enSilencio(const HoraLocal(3, 0), null, null), isFalse);
      expect(enSilencio(const HoraLocal(3, 0), noche, null), isFalse);
    });
  });

  group('fuera del silencio', () {
    test('lo que cae antes de medianoche sale a la mañana siguiente', () {
      final DateTime corrido =
          fueraDelSilencio(elMartes(23, 30), noche, manana);
      expect(corrido, DateTime(2026, 9, 16, 8, 0));
    });

    test('lo que cae después de medianoche sale el mismo día', () {
      final DateTime corrido = fueraDelSilencio(elMartes(3, 0), noche, manana);
      expect(corrido, DateTime(2026, 9, 15, 8, 0));
    });

    test('lo que no cae dentro no se toca', () {
      final DateTime intacto = elMartes(19, 0);
      expect(fueraDelSilencio(intacto, noche, manana), intacto);
    });

    test('correr nunca va hacia atrás', () {
      // Quien llame puede dar por hecho que un instante futuro sigue siendo
      // futuro después de correrlo. Si esto dejara de cumplirse, se programarían
      // avisos en el pasado y el plugin los descartaría en silencio.
      for (int h = 0; h < 24; h++) {
        final DateTime momento = elMartes(h, 30);
        expect(
          fueraDelSilencio(momento, noche, manana).isBefore(momento),
          isFalse,
          reason: 'a las $h:30 el recordatorio retrocedió',
        );
      }
    });
  });

  // ---------------------------------------------------------------------------
  // La cadena
  // ---------------------------------------------------------------------------

  /// Un espejo con todo en marcha y los valores de fábrica del Reino.
  const EspejoRecordatorio enMarcha = EspejoRecordatorio(
    intencionAvisos: true,
    permisoConcedido: true,
    modo: ModoRecordatorio.manual,
    horaManual: HoraLocal(19, 0),
    ultimaLlamada: true,
    silencioDesde: noche,
    silencioHasta: manana,
    horaPorDefecto: HoraLocal(19, 0),
    horaUltimaLlamada: HoraLocal(21, 30),
    ventanaDesde: HoraLocal(8, 0),
    ventanaHasta: HoraLocal(21, 30),
  );

  group('las puertas de apagado', () {
    test('sin intención no se programa nada', () {
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(intencionAvisos: false),
        elMartes(9),
      );
      expect(cadena, isEmpty);
    });

    test('sin permiso del sistema tampoco', () {
      // Es la mitad que faltaba: el aprendiz puede querer avisos y Android
      // puede estar negándolos. Programar en ese caso es escribir alarmas que
      // no se pintan.
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(permisoConcedido: false),
        elMartes(9),
      );
      expect(cadena, isEmpty);
    });

    test('con el recordatorio apagado tampoco', () {
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(modo: ModoRecordatorio.apagado),
        elMartes(9),
      );
      expect(cadena, isEmpty);
    });

    test('sin la hora del Reino no se inventa una', () {
      // Primer arranque sin red: la configuración pública no llegó. Antes que
      // clavar un 19:00 en Dart —que además sería un parámetro de juego como
      // literal— se prefiere no programar.
      const EspejoRecordatorio sinConfig = EspejoRecordatorio(
        intencionAvisos: true,
        permisoConcedido: true,
        modo: ModoRecordatorio.inteligente,
      );
      expect(planificarCadena(sinConfig, elMartes(9)), isEmpty);
    });
  });

  group('la cadena de tres días', () {
    test('a media mañana se programan los tres', () {
      final List<AvisoLocal> cadena = planificarCadena(enMarcha, elMartes(9));

      expect(cadena.map((AvisoLocal a) => a.id), <int>[1000, 1001, 1002, 1200]);
      expect(cadena[0].instante, DateTime(2026, 9, 15, 19, 0));
      expect(cadena[1].instante, DateTime(2026, 9, 16, 19, 0));
      expect(cadena[2].instante, DateTime(2026, 9, 17, 19, 0));
      // La última llamada es de hoy y solo de hoy.
      expect(cadena[3].instante, DateTime(2026, 9, 15, 21, 30));
    });

    test('los tres textos son distintos entre sí', () {
      // Repetir la misma frase tres noches seguidas es la vía más rápida a que
      // el aprendiz apague los avisos.
      final List<AvisoLocal> cadena = planificarCadena(enMarcha, elMartes(9));
      final Set<String> titulos =
          cadena.map((AvisoLocal a) => a.titulo).toSet();
      expect(titulos.length, cadena.length);
    });

    test('pasada la hora, el de hoy desaparece y quedan dos', () {
      final List<AvisoLocal> cadena = planificarCadena(enMarcha, elMartes(20));
      expect(cadena.map((AvisoLocal a) => a.id), <int>[1001, 1002, 1200]);
    });

    test('a quien ya practicó hoy no se le recuerda hoy', () {
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(ultimaPracticaLocal: elMartes(10)),
        elMartes(9),
      );
      // Ni el del día ni la última llamada: hoy ya está cumplido.
      expect(cadena.map((AvisoLocal a) => a.id), <int>[1001, 1002]);
    });

    test('todos aterrizan en Inicio', () {
      // El único destino que no promete que haya algo concreto esperando.
      final List<AvisoLocal> cadena = planificarCadena(enMarcha, elMartes(9));
      for (final AvisoLocal aviso in cadena) {
        expect(aviso.enlace, 'atenea://home');
      }
    });
  });

  group('el segundo aviso de la noche', () {
    test('sin el interruptor, no está', () {
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(ultimaLlamada: false),
        elMartes(9),
      );
      expect(cadena.map((AvisoLocal a) => a.id), isNot(contains(1200)));
    });

    test('no se programa si cae antes que la hora base', () {
      // Sería el primer aviso disfrazado de último: el aprendiz recibiría «se
      // acaba el día» a las 20:00 y «tu rato de hoy» a las 21:00.
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(
          horaManual: const HoraLocal(21, 0),
          horaUltimaLlamada: const HoraLocal(20, 0),
        ),
        elMartes(9),
      );
      expect(cadena.map((AvisoLocal a) => a.id), isNot(contains(1200)));
    });

    test('su texto no nombra la racha', () {
      // `last_call.min_streak` es una clave privada y la racha no se conoce
      // aquí, así que el texto no puede apoyarse en ella.
      expect(textoDeLaNoche.join(' ').toLowerCase(), isNot(contains('racha')));
    });
  });

  group('las reglas que sostienen los textos', () {
    test('la hora fuera de la franja del Reino se acota', () {
      // Es la grieta que se veía en la pantalla: el aprendiz elegía las 23:30,
      // Ajustes confirmaba «te avisaremos a las 23:30» y el servidor la movía a
      // las 21:30 sin decirlo. Ahora el teléfono acota igual que el servidor.
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(horaManual: const HoraLocal(23, 30)),
        elMartes(9),
      );
      expect(cadena.first.instante, DateTime(2026, 9, 15, 21, 30));
    });

    test('un aviso que al correrlo cambiaría de día se descarta', () {
      // Sin silencio por medio, una hora dentro de la franja de silencio no se
      // corre al día siguiente: se descarta. Decir «todavía no hay práctica de
      // hoy» el martes sobre un plan del lunes es hablar de otro día.
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(
          horaManual: const HoraLocal(23, 30),
          ventanaDesde: const HoraLocal(0, 0),
          ventanaHasta: const HoraLocal(23, 59),
        ),
        elMartes(9),
      );
      expect(cadena, isEmpty);
    });

    test('el margen antes del silencio deja pasar la última llamada justo', () {
      // 21:30 + 30 = 22:00, que es exactamente el inicio del silencio de
      // fábrica. Si alguien acorta el margen o mueve la hora, esto lo dirá.
      expect(margenAntesDelSilencio, 30);
      final List<AvisoLocal> cadena = planificarCadena(enMarcha, elMartes(9));
      expect(cadena.map((AvisoLocal a) => a.id), contains(1200));
    });

    test('lo que no deja margen suficiente no se programa', () {
      final List<AvisoLocal> cadena = planificarCadena(
        enMarcha.copiarCon(
          horaManual: const HoraLocal(21, 45),
          ventanaHasta: const HoraLocal(23, 0),
          ultimaLlamada: false,
        ),
        elMartes(9),
      );
      expect(cadena, isEmpty);
    });

    test('ningún aviso se programa en el pasado, mire a la hora que mire', () {
      // La red de seguridad. Un aviso en el pasado no falla: no suena.
      for (int h = 0; h < 24; h++) {
        final DateTime ahora = elMartes(h, 15);
        for (final AvisoLocal aviso in planificarCadena(enMarcha, ahora)) {
          expect(
            aviso.instante.isAfter(ahora),
            isTrue,
            reason: 'a las $h:15 el aviso ${aviso.id} cayó en ${aviso.instante}',
          );
        }
      }
    });
  });

  test('ningún texto local repite un titular del servidor', () {
    // Los ocho que escribe `planificador.py`. Copiar uno sería copiar una
    // afirmación que el teléfono no puede sostener: la racha caduca sola, las
    // misiones las calcula el Reino, y una alarma puesta anoche no sabe nada
    // del día en que suena.
    const Set<String> delServidor = <String>{
      'Tu racha de N días sigue en pie',
      'Tu racha aguanta un día más',
      'El Reino te espera',
      'Último tramo del día',
      'Tu aventura está donde la dejaste',
      'Una semana sin pisar el Reino',
      'Hace tiempo que no te vemos',
      'Encargos nuevos en el tablón',
    };

    final List<String> locales = <String>[
      ...textosDelDia.map((List<String> t) => t[0]),
      textoDeLaNoche[0],
    ];
    for (final String titulo in locales) {
      expect(
        delServidor,
        isNot(contains(titulo)),
        reason: '«$titulo» es del servidor: allí se redacta al entregarlo, '
            'aquí se redactó anoche.',
      );
    }
  });
}
