/// El recordatorio que el propio teléfono se pone, sin servidor de push.
///
/// Atenea ya sabe a quién avisar y cuándo: `avisos.py` y `planificador.py` lo
/// deciden con horas de silencio, topes diarios y claves de idempotencia, y lo
/// escriben en la bandeja. Lo que faltaba era el último metro —que algo suene
/// con la app cerrada— y ese metro no se cruza con Firebase, se cruza con una
/// alarma del propio aparato.
///
/// ## La invariante que sostiene todo esto
///
/// **La cadena de avisos solo existe mientras Atenea está cerrada.** Al volver
/// a primer plano se cancela entera; al salir se reconstruye entera.
///
/// Parece un detalle de ciclo de vida y es lo contrario: es lo que hace que los
/// textos sean ciertos. Si un aviso llega a sonar, es porque nadie abrió la app
/// desde que se programó, y eso no hay que recordarlo al redactar ni
/// comprobarlo al disparar: se cumple por construcción. De regalo, un aviso no
/// puede sonar con la app en primer plano, que es el ridículo clásico de
/// avisarte de que estudies mientras estás estudiando.
///
/// ## Lo que esta clase no hace
///
/// No decide nada. Qué avisos hay, a qué hora y con qué texto se calcula en
/// `plan_recordatorio.dart`, que es Dart puro y se puede probar sin teléfono.
/// Aquí solo se habla con Android.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:timezone/data/latest_all.dart' as datos_de_zonas;
import 'package:timezone/timezone.dart' as tz;

import '../datos/dtos.dart';
import 'memoria_recordatorio.dart';
import 'plan_recordatorio.dart';

/// Canal de Android donde vive el recordatorio.
///
/// Un canal y no varios: el aprendiz ve esta lista en los ajustes del sistema,
/// y ahí «Recordatorios» se entiende. «Recordatorio diario», «Última llamada» y
/// «Ausencia larga» por separado sería pedirle que administre tres cosas que
/// para él son una.
const String _idCanal = 'atenea_recordatorios';
const String _nombreCanal = 'Recordatorios';
const String _descripcionCanal =
    'El aviso para que no pierdas el hilo ni la racha.';

/// La campana del propio teléfono.
///
/// Se registra como observador del ciclo de vida en `iniciar()` y se da de baja
/// en `dispose()`. Lo hace ella sola para que `app.dart` no tenga que
/// convertirse en `StatefulWidget` solo por esto.
class RecordatorioLocal extends ChangeNotifier with WidgetsBindingObserver {
  RecordatorioLocal({
    FlutterLocalNotificationsPlugin? plugin,
    MemoriaRecordatorio? memoria,
  })  : _plugin = plugin ?? FlutterLocalNotificationsPlugin(),
        _memoria = memoria ?? MemoriaRecordatorio();

  final FlutterLocalNotificationsPlugin _plugin;
  final MemoriaRecordatorio _memoria;

  /// Lo último que este teléfono supo, y con lo que se arma la cadena.
  ///
  /// Se mantiene al día desde fuera —los ajustes del aprendiz, la configuración
  /// del Reino, la práctica del día— y se escribe en disco en cada cambio,
  /// porque el momento en que hace falta es justo aquel en que puede no haber
  /// red: cuando la aplicación se cierra.
  EspejoRecordatorio _espejo = const EspejoRecordatorio();
  EspejoRecordatorio get espejo => _espejo;

  /// Destino de un aviso que el aprendiz ya tocó y nadie ha atendido todavía.
  ///
  /// Vive aquí y no se navega directamente porque el toque puede llegar con la
  /// app cerrada del todo: en ese momento no hay enrutador, ni sesión, ni
  /// árbol de widgets. Quien pueda navegar lo recoge cuando pueda.
  String? _destinoPendiente;
  String? get destinoPendiente => _destinoPendiente;

  bool _listo = false;
  bool get listo => _listo;

  /// ¿Puede este teléfono mostrar avisos ahora mismo?
  ///
  /// Es un hecho del sistema operativo, no una preferencia: el aprendiz pudo
  /// revocarlo desde los ajustes de Android sin pasar por Atenea.
  bool _permitido = false;
  bool get permitido => _permitido;

  /// ¿Puede este aparato programar alarmas?
  ///
  /// La guarda no es contra excepciones sino contra algo peor. En web el plugin
  /// **tiene** implementación: acepta la llamada, no falla nada, y no programa
  /// nada, porque en un navegador no hay `AlarmManager`. Una excepción se ve;
  /// esto no. Y en escritorio la historia es parecida.
  ///
  /// Android y nada más, por tanto, que es donde vive Atenea hoy.
  bool get _hayAlarmas =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  // ---------------------------------------------------------------------------
  // Arranque
  // ---------------------------------------------------------------------------

  /// Prepara el plugin y las zonas horarias. Idempotente.
  ///
  /// No pide permiso: pedirlo al arrancar es la forma más rápida de que te lo
  /// nieguen para siempre. El permiso se pide donde tiene sentido, que es al
  /// encender el interruptor de Ajustes. Ver [pedirPermiso].
  Future<void> iniciar() async {
    if (_listo || !_hayAlarmas) return;

    datos_de_zonas.initializeTimeZones();
    // Sin esto `tz.local` es UTC, y una repetición diaria se desplazaría en
    // cada cambio de horario de verano sin que nada falle a la vista.
    try {
      final TimezoneInfo zona = await FlutterTimezone.getLocalTimezone();
      tz.setLocalLocation(tz.getLocation(zona.identifier));
    } catch (_) {
      // Zona desconocida o nombre que la base de datos no reconoce: se sigue
      // con UTC. Un recordatorio desplazado es mejor que ningún recordatorio, y
      // desde luego mejor que no arrancar.
    }

    await _plugin.initialize(
      settings: const InitializationSettings(
        // Un escudo monocromo, no el icono de lanzamiento. Android pinta este
        // recurso como silueta blanca y descarta el color, así que cualquier
        // icono con relleno sale como una mancha del tamaño del lienzo.
        //
        // El recurso lo busca el plugin **por nombre**, en tiempo de ejecución.
        // De ahí que esté listado en `android/app/src/main/res/raw/keep.xml`:
        // sin eso, `shrinkResources` lo borraría del APK de release sin que
        // nada fallase al compilar.
        android: AndroidInitializationSettings('@drawable/ic_aviso'),
      ),
      onDidReceiveNotificationResponse: _alTocarElAviso,
    );

    // El aprendiz pudo tocar un aviso con la app cerrada del todo. En ese caso
    // el toque no llega por la respuesta de arriba, sino por aquí.
    final NotificationAppLaunchDetails? arranque =
        await _plugin.getNotificationAppLaunchDetails();
    if (arranque?.didNotificationLaunchApp ?? false) {
      _anotarDestino(arranque?.notificationResponse?.payload);
    }

    _permitido = await _consultarPermiso();
    _espejo = (await _memoria.leer()).copiarCon(permisoConcedido: _permitido);
    _listo = true;
    WidgetsBinding.instance.addObserver(this);

    // La cadena de anoche se cancela aquí, y no puede esperar a un `resumed`.
    //
    // `didChangeAppLifecycleState` solo avisa de **cambios** de estado, y
    // registrarse como observador no reproduce el estado actual: en un arranque
    // en frío la aplicación ya está en primer plano cuando esto se ejecuta, así
    // que ese `resumed` no llega nunca. Sin esta línea, las alarmas programadas
    // al cerrar seguían armadas mientras el aprendiz estaba dentro de Atenea, y
    // podía sonarle «en este teléfono todavía no hay práctica de hoy» con la
    // aplicación abierta delante.
    //
    // Es justo la invariante que hace ciertos los textos: si un aviso suena, es
    // que nadie abrió la aplicación desde que se programó. Abrirla tiene que
    // borrarla, venga por donde venga.
    await cancelarTodo();

    notifyListeners();
  }

  @override
  void dispose() {
    if (_listo) WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  // ---------------------------------------------------------------------------
  // Permiso
  // ---------------------------------------------------------------------------

  /// Pide a Android el permiso de avisos y devuelve si quedó concedido.
  ///
  /// Este es el método que convierte el interruptor de Ajustes en un control de
  /// verdad. Durante mucho tiempo ese interruptor solo escribía un booleano en
  /// el servidor: decía «avisos en este dispositivo» sin preguntarle nada al
  /// dispositivo.
  ///
  /// Android solo muestra el diálogo una vez. Si el aprendiz ya dijo que no,
  /// esto devuelve `false` sin abrir nada, y quien llame tiene que contarlo
  /// —mandarlo a los ajustes del sistema— en vez de dejar el interruptor
  /// encendido mintiendo.
  Future<bool> pedirPermiso() async {
    if (!_hayAlarmas) return false;
    final AndroidFlutterLocalNotificationsPlugin? android = _android;
    if (android == null) return false;

    _permitido = await android.requestNotificationsPermission() ?? false;
    await _sincronizarPermisoEnElEspejo();
    notifyListeners();
    return _permitido;
  }

  /// Abre la pantalla de avisos de Atenea en los ajustes de Android.
  ///
  /// Es la única salida cuando el aprendiz ya dijo que no: a partir de la
  /// segunda negativa Android no vuelve a mostrar el diálogo, y
  /// [pedirPermiso] devuelve `false` sin abrir nada. Sin este camino, el
  /// interruptor rebotaría para siempre y sin explicación.
  Future<void> abrirAjustesDelSistema() async {
    if (!_hayAlarmas) return;
    await _android?.openAppNotificationSettings();
  }

  /// Vuelve a preguntar al sistema si los avisos siguen permitidos.
  ///
  /// Hace falta al volver a primer plano: el aprendiz puede haberlos apagado
  /// desde los ajustes de Android, y Atenea no se entera de ninguna otra forma.
  Future<bool> revisarPermiso() async {
    final bool antes = _permitido;
    _permitido = await _consultarPermiso();
    if (_permitido != antes) {
      await _sincronizarPermisoEnElEspejo();
      notifyListeners();
    }
    return _permitido;
  }

  /// El permiso es un hecho del aparato, y el espejo tiene que reflejarlo.
  ///
  /// Nunca al revés: de aquí no sale nada hacia el servidor. Que el aprendiz
  /// haya negado los avisos en este teléfono no puede apagar los del otro.
  Future<void> _sincronizarPermisoEnElEspejo() async {
    _espejo = _espejo.copiarCon(permisoConcedido: _permitido);
    await _memoria.guardar(_espejo);
  }

  Future<bool> _consultarPermiso() async {
    if (!_hayAlarmas) return false;
    return await _android?.areNotificationsEnabled() ?? false;
  }

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();

  // ---------------------------------------------------------------------------
  // La cadena
  // ---------------------------------------------------------------------------

  /// Borra la cadena entera.
  Future<void> cancelarTodo() async {
    if (!_hayAlarmas) return;
    await _plugin.cancelAll();
  }

  // ---------------------------------------------------------------------------
  // El espejo
  // ---------------------------------------------------------------------------

  /// Anota lo que el aprendiz eligió en Ajustes.
  ///
  /// Se llama desde el oyente de la sesión, así que **cualquier** cambio de la
  /// pantalla llega aquí sin añadir un gancho por interruptor: guardar ajustes
  /// termina siempre en `notifyListeners()`.
  Future<void> anotarAjustes(Ajustes? ajustes) async {
    if (ajustes == null) return;
    await _anotar((EspejoRecordatorio e) => e.copiarCon(
          intencionAvisos: ajustes.pushActivado,
          modo: ajustes.modoRecordatorio,
          horaManual: ajustes.horaRecordatorio,
          ultimaLlamada: ajustes.ultimaLlamadaActivada,
          silencioDesde: ajustes.silencioDesde,
          silencioHasta: ajustes.silencioHasta,
        ));
  }

  /// Anota lo que manda el Reino, sin tocar lo demás.
  ///
  /// Recibe la transformación en vez del controlador de configuración para no
  /// aprender aquí qué es `GET /config/public`: esta clase solo sabe de alarmas.
  Future<void> anotarDelReino(
    EspejoRecordatorio Function(EspejoRecordatorio) cambio,
  ) =>
      _anotar(cambio);

  /// Anota que hoy, en este teléfono, la práctica ya cuenta.
  ///
  /// Llega por dos caminos y los dos hacen falta. El panel dice si el Reino ya
  /// cuenta el día —y eso repara el caso de haber practicado desde otro
  /// aparato—; una lección o una evaluación recién terminada lo dice al
  /// instante, sin esperar al panel.
  Future<void> anotarPractica(EstadoDia? estado) async {
    if (estado == null || !estado.cuentaParaRacha) return;
    final DateTime ahora = DateTime.now();
    await _anotar((EspejoRecordatorio e) => e.copiarCon(
          ultimaPracticaLocal: DateTime(ahora.year, ahora.month, ahora.day),
        ));
  }

  /// Olvida todo al cerrar sesión: la cadena y el espejo.
  ///
  /// Sin esto, un teléfono compartido le diría a la siguiente persona «en este
  /// teléfono todavía no hay práctica de hoy» hablando de la práctica de otra, y
  /// la cuenta nueva heredaría las horas de la anterior.
  Future<void> olvidar() async {
    _espejo = const EspejoRecordatorio();
    await _memoria.olvidar();
    await cancelarTodo();
    notifyListeners();
  }

  /// Monta la cadena que corresponde ahora mismo.
  ///
  /// Es el único sitio donde se escriben alarmas, y se llama al irse a segundo
  /// plano. Antes de eso no hay nada que programar: con la aplicación delante,
  /// la cadena sobra.
  Future<void> sincronizar() =>
      reprogramar(planificarCadena(_espejo, DateTime.now()));

  Future<void> _anotar(
    EspejoRecordatorio Function(EspejoRecordatorio) cambio,
  ) async {
    _espejo = cambio(_espejo).copiarCon(permisoConcedido: _permitido);
    await _memoria.guardar(_espejo);
  }

  /// Sustituye la cadena por [avisos].
  ///
  /// **Primero programa y después cancela lo que sobra**, y ese orden no es
  /// casual. Cancelar primero parece más limpio, pero este método se llama
  /// cuando la aplicación se va a segundo plano, que es justo el momento en que
  /// Android es más propenso a matar el proceso: una muerte a mitad dejaría el
  /// teléfono con cero alarmas y sin nada corriendo que lo reparase. Así, lo
  /// peor que deja una muerte a medias es una alarma de más, y el siguiente
  /// cierre la limpia.
  ///
  /// Un identificador repetido **sustituye** al anterior en vez de apilarse, así
  /// que reprogramar no duplica nada.
  ///
  /// Un aviso cuyo instante ya pasó se descarta en vez de programarse: Android
  /// no se queja de una alarma en el pasado, sencillamente no suena, que es el
  /// peor de los dos comportamientos posibles.
  Future<void> reprogramar(List<AvisoLocal> avisos) async {
    if (!_hayAlarmas) return;

    final Set<int> puestos = <int>{};
    if (_permitido) {
      final tz.TZDateTime ahora = tz.TZDateTime.now(tz.local);
      for (final AvisoLocal aviso in avisos) {
        final tz.TZDateTime cuando =
            tz.TZDateTime.from(aviso.instante, tz.local);
        if (!cuando.isAfter(ahora)) continue;
        await _programar(aviso, cuando);
        puestos.add(aviso.id);
      }
    }

    // Lo que no se ha puesto en esta pasada, sobra. La lista de identificadores
    // es cerrada justamente para poder hacer esto sin preguntarle a Android qué
    // tiene pendiente.
    for (final int id in idsDeLaCadena) {
      if (!puestos.contains(id)) await _plugin.cancel(id: id);
    }
  }

  Future<void> _programar(AvisoLocal aviso, tz.TZDateTime cuando) =>
      _plugin.zonedSchedule(
        id: aviso.id,
        scheduledDate: cuando,
        title: aviso.titulo,
        body: aviso.cuerpo,
        payload: aviso.enlace,
        notificationDetails: const NotificationDetails(
          android: AndroidNotificationDetails(
            _idCanal,
            _nombreCanal,
            channelDescription: _descripcionCanal,
            importance: Importance.defaultImportance,
            priority: Priority.defaultPriority,
          ),
        ),
        // Inexacta a propósito: la alarma exacta pide permiso aparte desde
        // Android 14, o revisión de la tienda, y un recordatorio de estudio no
        // necesita el minuto clavado.
        //
        // El precio hay que decirlo entero, porque no son «unos minutos»:
        // `inexactAllowWhileIdle` está exento de Doze pero **no** de los cubos
        // de App Standby, y una aplicación que lleva dos días sin abrirse está
        // en el cubo más bajo, donde el aplazamiento se mide en horas. Por eso
        // ningún texto de la cadena lleva un reloj dentro, y por eso hay margen
        // antes del silencio en vez de apurar hasta el borde. El tercer día es
        // el menos fiable de los tres, y está asumido.
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      );

  // ---------------------------------------------------------------------------
  // Ciclo de vida: aquí vive la invariante
  // ---------------------------------------------------------------------------

  // El parámetro conserva el nombre inglés del framework porque es un
  // `override`: renombrarlo aquí es lo único de este archivo que el análisis
  // rechaza, y tiene razón —quien lea la firma la compara con la de Flutter.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      // Está mirando la app: sobra cualquier aviso. Y se revisa el permiso,
      // que puede haber cambiado en los ajustes de Android mientras no mirábamos.
      case AppLifecycleState.resumed:
        unawaited(revisarPermiso().then((_) => cancelarTodo()));

      // Se va. Ahora es cuando la cadena tiene sentido, y se monta con lo que
      // se sabe en este preciso instante.
      case AppLifecycleState.paused:
        unawaited(sincronizar());

      // `inactive` es una llamada entrante o el conmutador de apps: no es irse.
      // `hidden` y `detached` llegan sin margen para trabajo asíncrono fiable.
      case AppLifecycleState.inactive:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        break;
    }
  }

  // ---------------------------------------------------------------------------
  // El toque
  // ---------------------------------------------------------------------------

  void _alTocarElAviso(NotificationResponse respuesta) =>
      _anotarDestino(respuesta.payload);

  void _anotarDestino(String? enlace) {
    if (enlace == null || enlace.isEmpty) return;
    _destinoPendiente = enlace;
    notifyListeners();
  }

  /// Recoge el destino pendiente y lo olvida.
  ///
  /// Se consume una sola vez a propósito: si quien navega no pudo atenderlo
  /// —porque no había sesión, por ejemplo—, el destino se descarta en vez de
  /// quedarse esperando. Un enlace guardado que se abre tres arranques después
  /// lleva al aprendiz a un sitio que ya no tiene que ver con lo que tocó.
  String? tomarDestino() {
    final String? destino = _destinoPendiente;
    _destinoPendiente = null;
    return destino;
  }
}
