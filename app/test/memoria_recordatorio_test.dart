/// El espejo del recordatorio sobrevive al cierre, y se borra al salir.
///
/// El espejo existe porque el momento en que hace falta es el peor posible: la
/// aplicación se va a segundo plano, puede no haber red, y no hay tiempo para
/// una petición. Lo último que se supo tiene que estar en el disco.
///
/// Dos cosas se comprueban aquí, y la segunda es la que importa. Que el espejo
/// vaya y vuelva entero es higiene. Que `olvidar()` lo borre de verdad es el
/// caso del teléfono compartido: sin eso, la siguiente persona que entre recibe
/// un aviso que dice «en este teléfono todavía no hay práctica de hoy» hablando
/// de la práctica de otra, y hereda sus horas de silencio. Ninguna prueba de las
/// que había podía verlo, porque el fallo no está en el cálculo sino en lo que
/// queda escrito entre una sesión y la siguiente.
library;

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/nucleo/memoria_recordatorio.dart';
import 'package:atenea/nucleo/plan_recordatorio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late MemoriaRecordatorio memoria;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    memoria = MemoriaRecordatorio();
  });

  const EspejoRecordatorio lleno = EspejoRecordatorio(
    intencionAvisos: true,
    permisoConcedido: true,
    modo: ModoRecordatorio.manual,
    horaManual: HoraLocal(19, 30),
    ultimaLlamada: true,
    silencioDesde: HoraLocal(22, 0),
    silencioHasta: HoraLocal(8, 0),
    horaPorDefecto: HoraLocal(19, 0),
    horaUltimaLlamada: HoraLocal(21, 30),
    ventanaDesde: HoraLocal(8, 0),
    ventanaHasta: HoraLocal(21, 30),
  );

  test('un teléfono que estrena no programa nada', () {
    // Con el disco vacío no hay intención ni permiso, así que la primera puerta
    // de `planificarCadena` se cierra. Importa que el valor de partida sea ese
    // y no uno optimista: avisar a quien no lo ha pedido es peor que no avisar.
    const EspejoRecordatorio vacio = EspejoRecordatorio();
    expect(vacio.intencionAvisos, isFalse);
    expect(vacio.permisoConcedido, isFalse);
    expect(planificarCadena(vacio, DateTime(2026, 9, 15, 9)), isEmpty);
  });

  test('lo que se guarda es lo que se lee', () async {
    await memoria.guardar(lleno);
    final EspejoRecordatorio vuelto = await memoria.leer();

    expect(vuelto.intencionAvisos, isTrue);
    expect(vuelto.permisoConcedido, isTrue);
    expect(vuelto.modo, ModoRecordatorio.manual);
    expect(vuelto.horaManual?.texto, '19:30');
    expect(vuelto.ultimaLlamada, isTrue);
    expect(vuelto.silencioDesde?.texto, '22:00');
    expect(vuelto.silencioHasta?.texto, '08:00');
    expect(vuelto.horaPorDefecto?.texto, '19:00');
    expect(vuelto.horaUltimaLlamada?.texto, '21:30');
    expect(vuelto.ventanaDesde?.texto, '08:00');
    expect(vuelto.ventanaHasta?.texto, '21:30');
  });

  test('un espejo que va y vuelve planifica lo mismo', () async {
    // La prueba de arriba compara campos; esta compara la consecuencia, que es
    // lo que el aprendiz nota. Si algún día se añade un campo al espejo y nadie
    // lo persiste, aquí se verá.
    final DateTime ahora = DateTime(2026, 9, 15, 9);
    await memoria.guardar(lleno);

    final List<AvisoLocal> antes = planificarCadena(lleno, ahora);
    final List<AvisoLocal> despues =
        planificarCadena(await memoria.leer(), ahora);

    expect(despues.map((AvisoLocal a) => a.id), antes.map((AvisoLocal a) => a.id));
    expect(
      despues.map((AvisoLocal a) => a.instante),
      antes.map((AvisoLocal a) => a.instante),
    );
  });

  test('la fecha de práctica se guarda como día, sin hora', () async {
    // Se compara contra el día de calendario, así que arrastrar la hora solo
    // sirve para que dos valores del mismo día dejen de parecerse.
    await memoria.guardar(
      lleno.copiarCon(ultimaPracticaLocal: DateTime(2026, 9, 15, 17, 42)),
    );
    final EspejoRecordatorio vuelto = await memoria.leer();
    expect(vuelto.ultimaPracticaLocal, DateTime(2026, 9, 15));
  });

  test('al cerrar sesión no queda nada del aprendiz anterior', () async {
    await memoria.guardar(
      lleno.copiarCon(ultimaPracticaLocal: DateTime(2026, 9, 15)),
    );
    await memoria.olvidar();

    final EspejoRecordatorio vuelto = await memoria.leer();

    // Lo que importa no es que los campos estén vacíos, sino lo que se deduce de
    // eso: el teléfono no le va a decir nada a quien entre después.
    expect(vuelto.intencionAvisos, isFalse);
    expect(vuelto.permisoConcedido, isFalse);
    expect(vuelto.horaManual, isNull);
    expect(vuelto.silencioDesde, isNull);
    expect(vuelto.ultimaPracticaLocal, isNull);
    expect(planificarCadena(vuelto, DateTime(2026, 9, 15, 9)), isEmpty);
  });

  test('un disco corrupto no impide arrancar', () async {
    // Las preferencias las puede tocar cualquiera, y una versión vieja pudo
    // escribir otra cosa. Leer basura tiene que dar un espejo vacío, no una
    // excepción en el arranque de Atenea.
    SharedPreferences.setMockInitialValues(<String, Object>{
      'atenea_recordatorio_hora_manual': 'las siete y media',
      'atenea_recordatorio_modo': '翻译',
      'atenea_recordatorio_ultima_practica': 'ayer',
    });

    final EspejoRecordatorio vuelto = await MemoriaRecordatorio().leer();

    expect(vuelto.horaManual, isNull);
    expect(vuelto.ultimaPracticaLocal, isNull);
    // Un modo desconocido cae al de fábrica, que es lo que hace `desdeApi`.
    expect(vuelto.modo, ModoRecordatorio.inteligente);
  });
}
