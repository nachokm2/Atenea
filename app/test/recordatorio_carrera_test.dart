/// La carrera entre `resumed` y `paused`, por fin con red.
///
/// Es el caso que §3.1 del documento de traspaso llevaba anotado como
/// «arreglado pero sin prueba»: montarla exige falsear
/// `AndroidFlutterLocalNotificationsPlugin`, que el plugin resuelve por tipo
/// concreto, y abrir a mano la ventana entre las dos ramas.
///
/// La ventana se abre donde de verdad está: `revisarPermiso()` cruza un canal
/// de plataforma contra un hilo principal que está rearrancando la Activity, y
/// si el permiso cambió escribe doce claves en disco. Aquí eso se representa
/// con un `Completer` que la prueba suelta cuando quiere, así que la ventana es
/// exacta en vez de depender de un `pump` afortunado.
///
/// Lo que se fija es el **estado final observable**, no la implementación: si
/// el aprendiz abre Atenea y se sale mientras el permiso se está comprobando,
/// el teléfono se queda con su cadena de avisos puesta. Ninguna de las dos
/// piezas que lo sostienen —el `_enPrimerPlano` síncrono y la cola de un
/// hueco— aparece en las aserciones, para que se puedan cambiar por otra cosa
/// que cumpla lo mismo.
///
/// ## Lo que salió al comprobarla rompiendo el código
///
/// Las dos protecciones son **redundantes**, y eso no se deduce leyendo
/// ninguna de las dos:
///
/// * Quitar solo `if (_enPrimerPlano)` → verde. La cola serializa, así que el
///   cancelado corre antes de que `sincronizar` programe nada.
/// * Quitar solo la cola → verde. El guard ve `_enPrimerPlano` ya en falso.
/// * Quitar **las dos** → rojo, con el registro
///   `[zonedSchedule ×4, cancelAll]`: la cadena cancelada justo después de
///   ponerla, que es el daño que el comentario de
///   `didChangeAppLifecycleState` dice temer.
///
/// O sea que cualquiera de las dos sostiene la invariante hoy, y quien quite
/// una tiene que dejar la otra. Si alguien las toca a la vez, esta prueba se
/// pone roja: es lo único que lo impide.
///
/// La espera de diez milisegundos tras `paused` no es un `pump` afortunado: es
/// lo que hace que la cadena esté ya puesta cuando el permiso contesta. Sin
/// ella, programar y cancelar se resuelven en el mismo puñado de microtareas y
/// la prueba pasaba con las dos protecciones quitadas.
library;

import 'dart:async';

import 'package:atenea/datos/dtos.dart';
import 'package:atenea/nucleo/memoria_recordatorio.dart';
import 'package:atenea/nucleo/plan_recordatorio.dart';
import 'package:atenea/nucleo/recordatorio_local.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// El lado Android del plugin, con el permiso bajo control de la prueba.
class _AndroidFalso implements AndroidFlutterLocalNotificationsPlugin {
  /// Cada llamada a `areNotificationsEnabled` espera a que la prueba la suelte.
  final List<Completer<bool>> permisos = <Completer<bool>>[];

  @override
  Future<bool?> areNotificationsEnabled() {
    final Completer<bool> pendiente = Completer<bool>();
    permisos.add(pendiente);
    return pendiente.future;
  }

  /// Suelta la comprobación de permiso que está en curso.
  void conceder() => permisos.last.complete(true);

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// El plugin entero, anotando lo que se le pide y en qué orden.
class _PluginFalso implements FlutterLocalNotificationsPlugin {
  _PluginFalso(this.android);

  final _AndroidFalso android;

  /// Nombres de los métodos que se le pidieron, en orden de llamada.
  final List<String> pedido = <String>[];

  @override
  T? resolvePlatformSpecificImplementation<T extends FlutterLocalNotificationsPlatform>() =>
      android as T?;

  @override
  Future<bool?> initialize({
    required InitializationSettings settings,
    DidReceiveNotificationResponseCallback? onDidReceiveNotificationResponse,
    DidReceiveBackgroundNotificationResponseCallback?
        onDidReceiveBackgroundNotificationResponse,
  }) async {
    pedido.add('initialize');
    return true;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) {
    final String nombre = invocation.memberName
        .toString()
        .replaceAll('Symbol("', '')
        .replaceAll('")', '');
    pedido.add(nombre);
    return Future<void>.value();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const MethodChannel canalZona = MethodChannel('flutter_timezone');

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    // Sin esto `_hayAlarmas` es falso y el recordatorio no hace nada: todas
    // las aserciones pasarían sobre una clase apagada.
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    // `iniciar()` pregunta la zona horaria por un canal de plataforma. Sin
    // falsearlo el futuro no se completa nunca y la prueba se cuelga hasta el
    // tiempo límite, sin decir por qué.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canalZona, (MethodCall _) async {
      return 'America/Santiago';
    });
  });

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(canalZona, null);
  });

  Future<(RecordatorioLocal, _PluginFalso, _AndroidFalso)> arrancado() async {
    final _AndroidFalso android = _AndroidFalso();
    final _PluginFalso plugin = _PluginFalso(android);
    final RecordatorioLocal recordatorio = RecordatorioLocal(
      plugin: plugin,
      memoria: MemoriaRecordatorio(),
    );
    final Future<void> arranque = recordatorio.iniciar();
    // `iniciar()` también comprueba el permiso: se le concede y se espera.
    await Future<void>.delayed(Duration.zero);
    if (android.permisos.isNotEmpty && !android.permisos.last.isCompleted) {
      android.conceder();
    }
    await arranque;

    // Un aprendiz con los avisos puestos. Sin esto el espejo está vacío,
    // `planificarCadena` no devuelve nada y las pruebas medirían un teléfono
    // que no tenía avisos que perder: verdes y sin significado.
    await recordatorio.anotarDelReino(
      (EspejoRecordatorio e) => e.copiarCon(
        intencionAvisos: true,
        modo: ModoRecordatorio.manual,
        horaManual: const HoraLocal(19, 0),
        ultimaLlamada: true,
        horaPorDefecto: const HoraLocal(19, 0),
        horaUltimaLlamada: const HoraLocal(21, 30),
        ventanaDesde: const HoraLocal(8, 0),
        ventanaHasta: const HoraLocal(21, 30),
      ),
    );
    return (recordatorio, plugin, android);
  }

  test('salir mientras se comprueba el permiso no deja el móvil sin avisos',
      () async {
    final (RecordatorioLocal recordatorio, _PluginFalso plugin, _AndroidFalso android) =
        await arrancado();
    expect(recordatorio.listo, isTrue, reason: 'no llegó a arrancar');
    plugin.pedido.clear();

    // 1. Vuelve a Atenea. El trabajo se encola y se queda esperando al permiso.
    recordatorio.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await Future<void>.delayed(Duration.zero);
    expect(android.permisos, isNotEmpty, reason: 'no llegó a pedir el permiso');

    // 2. Y se sale **antes** de que el permiso conteste. Esta es la ventana.
    recordatorio.didChangeAppLifecycleState(AppLifecycleState.paused);

    // Se le da tiempo a que la salida haga su trabajo. Esto es lo que hace que
    // la prueba mida algo: sin esta espera, el programar y el cancelar se
    // resuelven en el mismo puñado de microtareas y el orden final depende del
    // azar del planificador, no del código. Con ella, la cadena ya está puesta
    // cuando el permiso contesta —que es exactamente el caso que el comentario
    // de `didChangeAppLifecycleState` dice temer: «cancelar entonces borraría
    // la cadena que `paused` acaba de programar».
    await Future<void>.delayed(const Duration(milliseconds: 10));

    // 3. Ahora contesta el permiso y se deja correr lo que quedaba.
    android.conceder();
    await Future<void>.delayed(const Duration(milliseconds: 20));

    // El estado final: quedan avisos puestos, y nada los canceló después.
    final int ultimoProgramado = plugin.pedido.lastIndexOf('zonedSchedule');
    final int ultimoCancelado = plugin.pedido.lastIndexOf('cancelAll');
    expect(
      ultimoProgramado,
      greaterThanOrEqualTo(0),
      reason: 'salir de la aplicación no programó ninguna cadena: ${plugin.pedido}',
    );
    expect(
      ultimoCancelado,
      lessThan(ultimoProgramado),
      reason: 'algo canceló la cadena después de programarla: ${plugin.pedido}',
    );
  });

  test('quedarse dentro sí cancela: la invariante por el otro lado', () async {
    // El contrapunto de la prueba anterior, y lo que impide «arreglarla»
    // quitando el cancelado: con Atenea delante no puede sonar nada.
    final (RecordatorioLocal recordatorio, _PluginFalso plugin, _AndroidFalso android) =
        await arrancado();
    plugin.pedido.clear();

    recordatorio.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await Future<void>.delayed(Duration.zero);
    android.conceder();
    await Future<void>.delayed(const Duration(milliseconds: 20));

    expect(
      plugin.pedido,
      contains('cancelAll'),
      reason: 'con la aplicación delante los avisos de anoche siguen armados',
    );
  });

  test('la cola no se atasca al ir y venir muchas veces', () async {
    // La cola es de un solo hueco y se encadena con `then`. Si algo encolado
    // esperase a algo encolado, se quedaría parada para siempre, sin excepción
    // y sin ruido: el recordatorio dejaría de programar nada y nadie lo vería.
    final (RecordatorioLocal recordatorio, _PluginFalso plugin, _AndroidFalso android) =
        await arrancado();
    plugin.pedido.clear();

    for (int vuelta = 0; vuelta < 5; vuelta++) {
      recordatorio.didChangeAppLifecycleState(AppLifecycleState.resumed);
      await Future<void>.delayed(Duration.zero);
      if (android.permisos.isNotEmpty && !android.permisos.last.isCompleted) {
        android.conceder();
      }
      recordatorio.didChangeAppLifecycleState(AppLifecycleState.paused);
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }

    expect(
      plugin.pedido,
      contains('zonedSchedule'),
      reason: 'tras cinco idas y venidas ya no programa: la cola se atascó',
    );
  });
}
