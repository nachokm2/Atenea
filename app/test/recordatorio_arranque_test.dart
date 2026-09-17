/// Un fallo del plugin de avisos no puede dejar Atenea sin arrancar.
///
/// `RecordatorioLocal.iniciar()` se llama desde el `Future.wait` de `main()`, y
/// ahí una excepción se lleva por delante el arranque entero. Media docena de
/// sus llamadas cruzan un canal de plataforma —inicializar el plugin, preguntar
/// por el aviso que abrió la aplicación, consultar el permiso, cancelar—, que es
/// exactamente lo que puede fallar en un teléfono concreto y en ninguna prueba.
///
/// El recordatorio es la última pieza que se añadió y la menos importante de
/// todas: la bandeja, la racha y las lecciones no dependen de él. Que su plugin
/// pueda impedir que el Reino abra era la peor relación posible entre las dos
/// cosas.
///
/// ## Lo que esta prueba no cubre, y conviene saberlo
///
/// El otro fallo del ciclo de vida —que `resumed` y `paused` se entrelacen y
/// dejen el teléfono sin ninguna alarma— **no tiene prueba**. Para montarla
/// haría falta falsear también `AndroidFlutterLocalNotificationsPlugin`, que es
/// una clase concreta que el plugin resuelve por tipo; sin ella el permiso sale
/// `false`, la cadena sale vacía y no hay nada que programar, así que la carrera
/// no se puede provocar. Queda anotado en `docs/PENDIENTE.md` en vez de fingir
/// cobertura con una prueba que pasaría siempre.
library;

import 'package:atenea/data/almacen_tokens.dart';
import 'package:atenea/nucleo/memoria_recordatorio.dart';
import 'package:atenea/nucleo/recordatorio_local.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Un plugin que revienta a la primera, como haría uno roto en un móvil real.
///
/// `noSuchMethod` cubre la superficie entera sin escribir una implementación
/// falsa por método: cualquier cosa que `RecordatorioLocal` le pida, falla.
class _PluginQueRevienta implements FlutterLocalNotificationsPlugin {
  /// Lo que se le llegó a pedir, en orden.
  final List<Symbol> pedido = <Symbol>[];

  int get llamadas => pedido.length;

  @override
  dynamic noSuchMethod(Invocation invocation) {
    pedido.add(invocation.memberName);
    throw PlatformException(
      code: 'roto',
      message: 'el canal de plataforma no responde',
    );
  }
}

/// Un almacen seguro que no se puede leer, como uno corrupto de verdad.
class _LlaveroRoto implements FlutterSecureStorage {
  @override
  dynamic noSuchMethod(Invocation invocation) => throw PlatformException(
        code: 'Exception encountered',
        message: 'no se pudo descifrar el almacen',
      );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('iniciar() no propaga el fallo del plugin', () async {
    final _PluginQueRevienta plugin = _PluginQueRevienta();
    final RecordatorioLocal recordatorio = RecordatorioLocal(
      plugin: plugin,
      memoria: MemoriaRecordatorio(),
    );

    // Lo que comprueba la prueba es justo lo que `main()` necesita: que esto se
    // pueda esperar sin un `try` alrededor.
    await expectLater(recordatorio.iniciar(), completes);

    expect(plugin.llamadas, greaterThan(0), reason: 'no llegó a usar el plugin');
  });

  test('con el plugin roto, el recordatorio queda apagado y lo dice', () async {
    final RecordatorioLocal recordatorio = RecordatorioLocal(
      plugin: _PluginQueRevienta(),
      memoria: MemoriaRecordatorio(),
    );

    await recordatorio.iniciar();

    // `listo` en falso es lo que impide que se registre el observador del ciclo
    // de vida. Con él puesto, cada ida a segundo plano llamaría a `sincronizar`
    // contra un plugin muerto —dentro de un `unawaited`, así que sin que nada
    // se viera— y el recordatorio aparentaría estar vivo.
    expect(recordatorio.listo, isFalse);

    // Y Ajustes lo pinta como bloqueado en vez de como encendido.
    expect(recordatorio.permitido, isFalse);
  });

  test('aunque el plugin no arranque, se intenta cancelar igual', () async {
    // Es la línea que sostiene la invariante en un arranque en frío, donde
    // `resumed` no llega nunca. Si el `catch` de `initialize` saliera con un
    // `return`, se la saltaría: el día que el plugin reviente, el aprendiz
    // abriría Atenea y le seguirían sonando los avisos de anoche con la
    // aplicación delante.
    //
    // Y se puede intentar: en el código Java del plugin, `cancelAll` baja a
    // `NotificationManagerCompat` y `AlarmManager` con el contexto que se fija
    // al enganchar el motor, no al inicializar.
    final _PluginQueRevienta plugin = _PluginQueRevienta();
    final RecordatorioLocal recordatorio = RecordatorioLocal(
      plugin: plugin,
      memoria: MemoriaRecordatorio(),
    );

    await recordatorio.iniciar();

    expect(plugin.pedido, contains(#initialize));
    expect(
      plugin.pedido,
      contains(#cancelAll),
      reason: 'salir por el catch se lleva por delante la invariante',
    );
  });

  test('llamar dos veces tampoco propaga', () async {
    // `iniciar()` es idempotente, y el camino de fallo no debe cambiar eso: si
    // alguien lo reintenta —un `main()` que se reconstruya, una prueba— tiene
    // que seguir sin lanzar.
    final RecordatorioLocal recordatorio = RecordatorioLocal(
      plugin: _PluginQueRevienta(),
      memoria: MemoriaRecordatorio(),
    );

    await expectLater(recordatorio.iniciar(), completes);
    await expectLater(recordatorio.iniciar(), completes);
  });

  test('un almacén de claves roto tampoco impide arrancar', () async {
    // El otro futuro del mismo `Future.wait` de `main()`. Un almacén de claves
    // corrupto —tras una actualización del sistema, o al restaurar una copia en
    // un teléfono distinto— lanza al leer, y eso dejaba a Atenea sin abrir.
    //
    // Es de la misma familia que el fallo del plugin y bastante más probable.
    final AlmacenTokens tokens = AlmacenTokens(seguro: _LlaveroRoto());

    await expectLater(tokens.cargar(), completes);

    // Sin tokens: el aprendiz ve la pantalla de acceso y vuelve a entrar. Su
    // progreso está en el Reino, no aquí.
    expect(tokens.haySesion, isFalse);
    expect(tokens.acceso, isNull);
  });

  test('el recordatorio apagado no programa nada', () async {
    // La consecuencia que importa: con el plugin roto, pedirle que sincronice
    // tampoco puede lanzar, porque `sincronizar()` se llama con `unawaited`
    // desde el ciclo de vida y una excepción ahí ensucia la zona entera.
    final RecordatorioLocal recordatorio = RecordatorioLocal(
      plugin: _PluginQueRevienta(),
      memoria: MemoriaRecordatorio(),
    );
    await recordatorio.iniciar();

    // Sin permiso ni intención, la cadena sale vacía y no se toca el plugin.
    await expectLater(recordatorio.sincronizar(), completes);
  });
}
