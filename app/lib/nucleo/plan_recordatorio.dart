/// Cuándo debe sonar el recordatorio del propio teléfono.
///
/// Este archivo no toca Android, ni el plugin de notificaciones, ni el reloj
/// del sistema: todo entra por parámetro. Esa es la razón de que exista
/// separado de `recordatorio_local.dart`, y no es una manía de arquitectura.
/// La lógica de «qué hora toca» es la única parte del recordatorio que se puede
/// equivocar en silencio —el aviso suena a deshora y nadie se entera hasta que
/// un aprendiz se queja—, y también la única que `flutter test` puede
/// comprobar sin un teléfono delante.
///
/// Las reglas no se inventan aquí: son las del servidor, traducidas. El
/// original vive en `backend/app/modules/gamification/avisos.py` (`en_silencio`
/// y `fuera_del_silencio`) y ya está probado en Python. Si algún día cambian
/// allí, esto se queda viejo sin avisar, así que la prueba de este archivo cita
/// los casos concretos que el servidor documenta.
library;

import '../datos/dtos.dart';

/// Un aviso ya decidido, listo para que Android lo programe.
///
/// [instante] es hora de pared local y a secas: «las 19:00 del martes», sin
/// zona pegada. La traducción a la zona con nombre que exige `zonedSchedule` la
/// hace `recordatorio_local.dart`, y se hace allí a propósito, porque es la
/// única capa que sabe en qué zona está el teléfono de verdad.
///
/// [enlace] es un `atenea://…` de los que ya traduce `EnlacesProfundos`: al
/// tocar el aviso no hay que inventar navegación, solo entregar esta cadena.
class AvisoLocal {
  const AvisoLocal({
    required this.id,
    required this.instante,
    required this.titulo,
    required this.cuerpo,
    required this.enlace,
  });

  /// Identificador estable dentro de la cadena, para poder cancelarlo.
  final int id;

  /// Cuándo suena, en hora local de pared.
  final DateTime instante;

  final String titulo;
  final String cuerpo;

  /// Destino al tocarlo, en forma `atenea://…`.
  final String enlace;

  @override
  String toString() => 'AvisoLocal($id, $instante, «$titulo»)';
}

/// Minutos desde medianoche. Compara horas sin pelearse con las fechas.
int _minutos(HoraLocal h) => h.hora * 60 + h.minuto;

/// El día de calendario [desplazamiento] días después de [base], a medianoche.
///
/// **No vale `add(Duration(days: n))` para esto.** Esa suma añade 24 horas de
/// reloj, y un día de calendario no siempre dura 24 horas: el domingo en que
/// los relojes atrasan dura 25, así que medianoche más 24 horas son las 23:00
/// del *mismo* día. Con eso, «mañana» y «hoy» salían con la misma fecha y dos
/// avisos de la cadena se pisaban. Chile cambia la hora dos veces al año.
///
/// Sumar al componente `day` deja que Dart normalice el calendario —el 32 de
/// enero es el 1 de febrero— sin que el reloj intervenga.
DateTime _dia(DateTime base, int desplazamiento) =>
    DateTime(base.year, base.month, base.day + desplazamiento);

/// ¿Cae `hora` dentro de la franja de silencio?
///
/// La franja cruza la medianoche cuando el inicio es mayor que el fin, que es
/// el caso por defecto (22:00 → 08:00).
///
/// Inicio igual que fin se lee como **sin silencio**, no como silencio de
/// veinticuatro horas. Es la misma decisión que toma el servidor, y por la
/// misma razón: la otra lectura dejaría al aprendiz sin ningún aviso sin que él
/// lo haya pedido.
bool enSilencio(HoraLocal hora, HoraLocal? desde, HoraLocal? hasta) {
  if (desde == null || hasta == null) return false;
  final int h = _minutos(hora);
  final int i = _minutos(desde);
  final int f = _minutos(hasta);
  if (i == f) return false;
  if (i < f) return h >= i && h < f;
  return h >= i || h < f;
}

/// Corre un instante hasta el final del silencio si cae dentro.
///
/// Correr y no descartar, igual que el servidor: un recordatorio que cae a las
/// tres de la madrugada no se pierde, se entrega cuando el aprendiz puede
/// leerlo. Descartarlo sería castigar a quien eligió una hora incómoda.
///
/// El resultado nunca va hacia atrás, y eso importa: quien llame a esto puede
/// dar por hecho que un instante futuro sigue siendo futuro después de correrlo.
DateTime fueraDelSilencio(DateTime momento, HoraLocal? desde, HoraLocal? hasta) {
  final HoraLocal hora = HoraLocal(momento.hour, momento.minute);
  if (!enSilencio(hora, desde, hasta)) return momento;

  // Con la franja cruzando la medianoche hay dos mitades: lo que cae antes de
  // medianoche sale al día siguiente, lo que cae después sale hoy mismo.
  final bool cruzaMedianoche = _minutos(desde!) > _minutos(hasta!);
  final bool esLaMitadDeAntes = cruzaMedianoche && _minutos(hora) >= _minutos(desde);
  final DateTime dia = esLaMitadDeAntes ? _dia(momento, 1) : momento;

  return DateTime(dia.year, dia.month, dia.day, hasta.hora, hasta.minuto);
}

/// Aprieta una hora contra los bordes de la franja de recordatorios.
///
/// Gemelo de `acotar()` en `planificador.py`. El servidor lo aplica siempre, así
/// que el teléfono tiene que aplicarlo también: si no, la pantalla promete las
/// 23:30, el aviso local suena a las 23:30 y el del Reino llega a las 21:30.
HoraLocal acotar(HoraLocal hora, HoraLocal? inicio, HoraLocal? fin) {
  if (inicio == null || fin == null) return hora;
  if (_minutos(hora) < _minutos(inicio)) return inicio;
  if (_minutos(hora) > _minutos(fin)) return fin;
  return hora;
}

/// Margen antes del silencio, en minutos.
///
/// **No es un parámetro de juego y no va a `game_configs`.** Es una propiedad
/// del mecanismo de entrega, no una decisión de producto: la alarma se programa
/// con `inexactAllowWhileIdle`, que Android puede aplazar. Sin este margen se
/// construye un gemelo cuidadoso de `fuera_del_silencio` y acto seguido se
/// elige un modo de alarma que lo viola igual.
///
/// Con los valores de fábrica la última llamada cabe justo: 21:30 + 30 = 22:00,
/// que es exactamente el inicio del silencio.
const int margenAntesDelSilencio = 30;

/// Lo que el teléfono sabe cuando la app se va a segundo plano.
///
/// Tres clases de dato, y la distinción es la que sostiene el diseño:
///
/// - **Lo que el aprendiz eligió** — viaja del servidor en `Ajustes`.
/// - **Lo que manda el Reino** — viene de `GET /config/public`. Ninguna de esas
///   horas se escribe a mano en Dart: son parámetros de juego y viven en
///   `game_configs`. Si falta una, no se programa lo que dependa de ella; nunca
///   se inventa un 19:00.
/// - **Lo que solo sabe este aparato** — el permiso del sistema operativo y la
///   última fecha en que aquí hubo práctica.
class EspejoRecordatorio {
  const EspejoRecordatorio({
    this.intencionAvisos = false,
    this.permisoConcedido = false,
    this.modo = ModoRecordatorio.inteligente,
    this.horaManual,
    this.ultimaLlamada = false,
    this.silencioDesde,
    this.silencioHasta,
    this.horaPorDefecto,
    this.horaUltimaLlamada,
    this.ventanaDesde,
    this.ventanaHasta,
    this.ultimaPracticaLocal,
  });

  /// «Quiero que mi teléfono me avise». Es de la cuenta (`push_enabled`).
  final bool intencionAvisos;

  /// «Este aparato puede». Es del sistema operativo y nunca viaja al servidor.
  ///
  /// Son dos cosas distintas a propósito: la intención es de la cuenta y el
  /// permiso es del aparato. Confundirlos hace que negar el permiso en el móvil
  /// viejo apague los avisos del nuevo.
  final bool permisoConcedido;

  final ModoRecordatorio modo;
  final HoraLocal? horaManual;
  final bool ultimaLlamada;
  final HoraLocal? silencioDesde;
  final HoraLocal? silencioHasta;

  /// `notifications.reminder.default_hour`.
  final HoraLocal? horaPorDefecto;

  /// `notifications.last_call.hour`.
  final HoraLocal? horaUltimaLlamada;

  /// Los dos bordes de `notifications.reminder.window`.
  final HoraLocal? ventanaDesde;
  final HoraLocal? ventanaHasta;

  /// Último día en que **este** teléfono vio que la práctica contaba.
  final DateTime? ultimaPracticaLocal;

  EspejoRecordatorio copiarCon({
    bool? intencionAvisos,
    bool? permisoConcedido,
    ModoRecordatorio? modo,
    HoraLocal? horaManual,
    bool? ultimaLlamada,
    HoraLocal? silencioDesde,
    HoraLocal? silencioHasta,
    HoraLocal? horaPorDefecto,
    HoraLocal? horaUltimaLlamada,
    HoraLocal? ventanaDesde,
    HoraLocal? ventanaHasta,
    DateTime? ultimaPracticaLocal,
  }) =>
      EspejoRecordatorio(
        intencionAvisos: intencionAvisos ?? this.intencionAvisos,
        permisoConcedido: permisoConcedido ?? this.permisoConcedido,
        modo: modo ?? this.modo,
        horaManual: horaManual ?? this.horaManual,
        ultimaLlamada: ultimaLlamada ?? this.ultimaLlamada,
        silencioDesde: silencioDesde ?? this.silencioDesde,
        silencioHasta: silencioHasta ?? this.silencioHasta,
        horaPorDefecto: horaPorDefecto ?? this.horaPorDefecto,
        horaUltimaLlamada: horaUltimaLlamada ?? this.horaUltimaLlamada,
        ventanaDesde: ventanaDesde ?? this.ventanaDesde,
        ventanaHasta: ventanaHasta ?? this.ventanaHasta,
        ultimaPracticaLocal: ultimaPracticaLocal ?? this.ultimaPracticaLocal,
      );
}

/// Los cuatro textos del recordatorio local, y el porqué de cada renuncia.
///
/// **Ninguno es un texto del servidor**, y eso es deliberado. El servidor
/// escribe ocho titulares —«Tu racha de N días sigue en pie», «El Reino te
/// espera», «Último tramo del día»…— y copiarlos aquí sería copiar afirmaciones
/// que el teléfono no puede sostener. Hay una prueba que vigila que las dos
/// listas no se toquen nunca.
///
/// Lo que estos textos renuncian a decir, a propósito:
///
/// - **La racha.** Es la palanca más eficaz que existe y se deja fuera: su
///   longitud caduca sola con el paso del tiempo, y decir «tus 12 días» con un
///   dato de hace cinco es exactamente la mentira que todo esto existe para no
///   cometer.
/// - **Misiones y rutas.** Las calcula el servidor. Una alarma programada
///   anoche no puede saber qué hay hoy en el tablón.
/// - **La hora.** «Son las 19:00» es cierto hasta que el aprendiz cruza un
///   huso; y sin eso, la alarma inexacta puede llegar horas tarde si Android
///   tiene la aplicación en reposo profundo.
///
/// Los tres primeros son distintos entre sí porque repetir la misma frase tres
/// noches seguidas es la vía más rápida a que el aprendiz apague los avisos. Y
/// «desde ayer» y «dos días» son tan ciertos como el resto por el mismo
/// argumento: si el aviso llegó a sonar, es que nadie abrió la aplicación.
const List<List<String>> textosDelDia = <List<String>>[
  <String>[
    'Tu rato de hoy',
    'En este teléfono todavía no hay práctica de hoy. Un rato corto y retomas '
        'el hilo.',
  ],
  <String>[
    'Atenea sigue abierta',
    'Desde ayer este teléfono no registra práctica. Volver cuesta menos de lo '
        'que parece.',
  ],
  <String>[
    'Dos días de pausa',
    'Este teléfono lleva dos días sin registrar práctica. Una lección corta '
        'basta para retomarlo.',
  ],
];

/// El segundo aviso de la noche. Ver [textosDelDia] para las renuncias.
const List<String> textoDeLaNoche = <String>[
  'Se acaba el día',
  'Y en este teléfono todavía no hay práctica de hoy. Si te quedan diez '
      'minutos, el Reino sigue abierto.',
];

/// Todos los identificadores que esta cadena puede llegar a ocupar.
///
/// La lista es cerrada a propósito: quien escribe las alarmas cancela justo los
/// que no ha programado, y para eso necesita saberlos todos.
const List<int> idsDeLaCadena = <int>[1000, 1001, 1002, 1200];

/// Único destino de los cuatro avisos.
///
/// `atenea://home` ya lo traduce `EnlacesProfundos`, y es el único sitio que no
/// promete que haya algo concreto esperando. Mandar a una ruta o a una misión
/// sería afirmar que existe.
const String enlaceDelAviso = 'atenea://home';

/// La cadena de avisos que hay que dejar puesta al cerrar la aplicación.
///
/// Devuelve la lista vacía en cuanto una puerta se cierra: sin intención, sin
/// permiso o con el recordatorio apagado no se programa nada.
///
/// Se calcula entera de una vez, y no aviso a aviso, porque la cadena es la
/// unidad que tiene sentido: se pone al salir y se borra al volver. Si un aviso
/// del desfase *k* llega a sonar es porque nadie abrió Atenea desde que se
/// programó, y por eso su texto es cierto por construcción y no por cuidado al
/// redactarlo.
List<AvisoLocal> planificarCadena(
  EspejoRecordatorio espejo,
  DateTime ahoraLocal,
) {
  // Regla 1 — las puertas de apagado.
  if (!espejo.intencionAvisos ||
      !espejo.permisoConcedido ||
      espejo.modo == ModoRecordatorio.apagado) {
    return const <AvisoLocal>[];
  }

  // Regla 2 — la hora base, acotada a la franja del Reino.
  //
  // En modo inteligente el servidor calcula la mediana de la hora habitual de
  // los últimos catorce días. El teléfono no tiene esa tabla, así que usa la
  // hora por defecto del Reino. Es la única aproximación del plan y es
  // consciente: sin esa hora no se programa nada, en vez de inventar un 19:00.
  final HoraLocal? elegida = espejo.modo == ModoRecordatorio.manual
      ? (espejo.horaManual ?? espejo.horaPorDefecto)
      : espejo.horaPorDefecto;
  if (elegida == null) return const <AvisoLocal>[];
  final HoraLocal base =
      acotar(elegida, espejo.ventanaDesde, espejo.ventanaHasta);

  final DateTime hoy =
      DateTime(ahoraLocal.year, ahoraLocal.month, ahoraLocal.day);
  final DateTime? practica = espejo.ultimaPracticaLocal;
  final bool practicadoHoy = practica != null &&
      DateTime(practica.year, practica.month, practica.day) == hoy;

  final List<AvisoLocal> cadena = <AvisoLocal>[];

  // Regla 3 — los tres desfases: hoy, mañana y pasado.
  for (int k = 0; k < textosDelDia.length; k++) {
    // El de hoy sobra si el día ya está cumplido en este teléfono.
    if (k == 0 && practicadoHoy) continue;

    final DateTime? instante =
        _instanteValido(base, _dia(hoy, k), ahoraLocal, espejo);
    if (instante == null) continue;

    cadena.add(AvisoLocal(
      id: idsDeLaCadena[k],
      instante: instante,
      titulo: textosDelDia[k][0],
      cuerpo: textosDelDia[k][1],
      enlace: enlaceDelAviso,
    ));
  }

  // Regla 7 — el segundo aviso de la noche. Solo hoy, solo si el aprendiz lo
  // quiere, y solo si cae después de la hora base: antes sería el primer aviso
  // disfrazado de último.
  //
  // No se honra `last_call.min_streak` porque es una clave privada y la racha
  // no se conoce aquí. Por eso este texto tampoco la nombra.
  final HoraLocal? noche = espejo.horaUltimaLlamada;
  if (espejo.ultimaLlamada &&
      !practicadoHoy &&
      noche != null &&
      _minutos(noche) > _minutos(base)) {
    final DateTime? instante = _instanteValido(noche, hoy, ahoraLocal, espejo);
    if (instante != null) {
      cadena.add(AvisoLocal(
        id: idsDeLaCadena[3],
        instante: instante,
        titulo: textoDeLaNoche[0],
        cuerpo: textoDeLaNoche[1],
        enlace: enlaceDelAviso,
      ));
    }
  }

  return _unaVozPorInstante(cadena);
}

/// Descarta los avisos que caerían a la vez que otro anterior.
///
/// El caso que esto arregla no se ve con la franja de fábrica, y por eso las
/// primeras pruebas no lo cazaron: pide unas horas de silencio que **no** crucen
/// la medianoche —de 12:00 a 22:00, el turno de noche— con el recordatorio a las
/// 13:00. El aviso del día cae dentro del silencio y se corre a las 22:00; la
/// última llamada de las 21:30 cae dentro y se corre a las 22:00 también. La
/// regla que descarta lo que cambia de día no los toca, porque ninguno lo hace.
///
/// El resultado eran dos notificaciones en el mismo segundo diciendo cosas
/// distintas: «todavía no hay práctica de hoy» y «se acaba el día».
///
/// Gana el primero de la cadena, que está ordenada por cercanía: el recordatorio
/// del día antes que el de la noche. Es la elección menos sorprendente —el
/// aprendiz recibe el aviso normal, no el de urgencia— y sobre todo es
/// determinista, que importa más que cuál de los dos sobreviva.
List<AvisoLocal> _unaVozPorInstante(List<AvisoLocal> cadena) {
  final Set<DateTime> ocupados = <DateTime>{};
  return <AvisoLocal>[
    for (final AvisoLocal aviso in cadena)
      if (ocupados.add(aviso.instante)) aviso,
  ];
}

/// El instante de un aviso, o `null` si no debe programarse.
///
/// Aquí viven las reglas 4, 5 y 6, y las tres descartan por razones distintas.
DateTime? _instanteValido(
  HoraLocal hora,
  DateTime dia,
  DateTime ahoraLocal,
  EspejoRecordatorio espejo,
) {
  final DateTime deseado =
      DateTime(dia.year, dia.month, dia.day, hora.hora, hora.minuto);

  // Ya pasó. Programar en el pasado no falla: simplemente no suena.
  if (!deseado.isAfter(ahoraLocal)) return null;

  // Regla 6 — el margen antes del silencio. Un aviso puesto justo en el borde
  // se convierte en un aviso dentro del silencio en cuanto Android lo aplaza.
  final HoraLocal? inicio = espejo.silencioDesde;
  final HoraLocal? fin = espejo.silencioHasta;
  if (inicio != null && fin != null) {
    // Solo cuando la franja cruza la medianoche: si el silencio está en mitad
    // del día, acercarse a su borde por abajo no es estar a punto de entrar.
    final bool cruza = _minutos(inicio) > _minutos(fin);
    if (cruza && _minutos(hora) + margenAntesDelSilencio > _minutos(inicio)) {
      return null;
    }
  }

  // Regla 4 — correr fuera del silencio, como hace el servidor.
  final DateTime corrido = fueraDelSilencio(deseado, inicio, fin);

  // Regla 5 — si al correrlo cambió de día, se descarta.
  //
  // Es la regla que sostiene los textos. Un aviso del lunes que suena el martes
  // a las 08:00 diciendo «todavía no hay práctica de hoy» habla de un día
  // distinto del que el aprendiz está viviendo. Descartarlo es más honesto que
  // entregarlo tarde, y es lo contrario de lo que hace el servidor —que puede
  // correrlo— porque el servidor redacta el texto en el momento de entregarlo y
  // una alarma local lo redactó anoche.
  if (corrido.year != deseado.year ||
      corrido.month != deseado.month ||
      corrido.day != deseado.day) {
    return null;
  }

  return corrido.isAfter(ahoraLocal) ? corrido : null;
}
