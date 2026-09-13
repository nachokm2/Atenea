/// DTO de todas las respuestas de la API de Atenea (§7 del contrato).
///
/// Reglas que se cumplen sin excepción en este archivo:
///
/// - Ningún `desdeJson` lanza: un campo ausente, nulo o de otro tipo cae al
///   valor por defecto documentado.
/// - Las claves JSON son literalmente las del contrato (`snake_case`); los
///   identificadores Dart van en español.
/// - Los identificadores de entidad son `String` (UUID en texto).
/// - Las marcas de tiempo llegan en UTC ISO-8601 y se exponen en hora local
///   con [fechaHora]; los días de calendario se conservan con [fechaDia].
/// - La app **nunca** calcula XP, oro, nivel, dominio ni precios: todo llega
///   resuelto en [ReciboRecompensas] y en las respuestas del servidor.
library;

import 'modelos.dart';

export 'modelos.dart';

// ---------------------------------------------------------------------------
// Utilidades de lectura tolerante
// ---------------------------------------------------------------------------

String _txt(Object? valor, [String porDefecto = '']) {
  if (valor == null) return porDefecto;
  if (valor is String) return valor;
  return valor.toString();
}

String? _txtN(Object? valor) {
  if (valor == null) return null;
  final String texto = valor is String ? valor : valor.toString();
  return texto.isEmpty ? null : texto;
}

int _ent(Object? valor, [int porDefecto = 0]) {
  if (valor is int) return valor;
  if (valor is num) return valor.round();
  if (valor is bool) return valor ? 1 : 0;
  if (valor is String) {
    final String limpio = valor.trim();
    return int.tryParse(limpio) ?? double.tryParse(limpio)?.round() ?? porDefecto;
  }
  return porDefecto;
}

int? _entN(Object? valor) => valor == null ? null : _ent(valor);

double _dec(Object? valor, [double porDefecto = 0]) {
  if (valor is double) return valor;
  if (valor is num) return valor.toDouble();
  if (valor is String) return double.tryParse(valor.trim()) ?? porDefecto;
  return porDefecto;
}

double? _decN(Object? valor) => valor == null ? null : _dec(valor);

bool _bol(Object? valor, [bool porDefecto = false]) {
  if (valor is bool) return valor;
  if (valor is num) return valor != 0;
  if (valor is String) {
    final String v = valor.trim().toLowerCase();
    if (v == 'true' || v == '1' || v == 'si' || v == 'sí') return true;
    if (v == 'false' || v == '0' || v == 'no' || v.isEmpty) return false;
  }
  return porDefecto;
}

Map<String, dynamic> _mapa(Object? valor) =>
    valor is Map ? Map<String, dynamic>.from(valor) : <String, dynamic>{};

Map<String, dynamic>? _mapaN(Object? valor) =>
    valor is Map ? Map<String, dynamic>.from(valor) : null;

List<T> _lista<T>(Object? valor, T Function(Map<String, dynamic> json) desde) {
  if (valor is! List) return <T>[];
  final List<T> salida = <T>[];
  for (final Object? bruto in valor) {
    if (bruto is Map) salida.add(desde(Map<String, dynamic>.from(bruto)));
  }
  return salida;
}

List<String> _textos(Object? valor) {
  if (valor is! List) return const <String>[];
  final List<String> salida = <String>[];
  for (final Object? bruto in valor) {
    if (bruto == null) continue;
    salida.add(bruto.toString());
  }
  return salida;
}

Map<String, String?> _mapaTextos(Object? valor) {
  if (valor is! Map) return const <String, String?>{};
  final Map<String, String?> salida = <String, String?>{};
  valor.forEach((Object? clave, Object? v) {
    salida[clave.toString()] = v?.toString();
  });
  return salida;
}

/// Devuelve el primer valor no nulo de [claves] dentro de [json].
Object? _alguna(Map<String, dynamic> json, List<String> claves) {
  for (final String clave in claves) {
    final Object? v = json[clave];
    if (v != null) return v;
  }
  return null;
}

/// Hora local del usuario (`"21:30:00"`), sin depender de Flutter.
class HoraLocal {
  const HoraLocal(this.hora, this.minuto);

  /// Lee `"HH:MM"` o `"HH:MM:SS"`; devuelve `null` si no es una hora válida.
  static HoraLocal? desdeTexto(Object? valor) {
    final String? texto = _txtN(valor);
    if (texto == null) return null;
    final List<String> partes = texto.split(':');
    if (partes.length < 2) return null;
    final int? h = int.tryParse(partes[0].trim());
    final int? m = int.tryParse(partes[1].trim());
    if (h == null || m == null || h < 0 || h > 23 || m < 0 || m > 59) return null;
    return HoraLocal(h, m);
  }

  /// Hora del día, 0–23.
  final int hora;

  /// Minuto, 0–59.
  final int minuto;

  /// Formato `"HH:MM"` para mostrar y para enviar a la API.
  String get texto =>
      '${hora.toString().padLeft(2, '0')}:${minuto.toString().padLeft(2, '0')}';

  @override
  String toString() => texto;
}

// ---------------------------------------------------------------------------
// §7.1 Autenticación y cuenta
// ---------------------------------------------------------------------------

/// Par de tokens emitido por `register`, `login` y `refresh` (`AuthTokens`).
class TokensAuth {
  const TokensAuth({
    required this.acceso,
    required this.refresco,
    this.tipo = 'bearer',
    this.expiraEnSegundos = 0,
    this.usuario,
  });

  /// Lee `{access_token, refresh_token, token_type, expires_in, user}`.
  factory TokensAuth.desdeJson(Map<String, dynamic> json) => TokensAuth(
        acceso: _txt(json['access_token']),
        refresco: _txt(json['refresh_token']),
        tipo: _txt(json['token_type'], 'bearer'),
        expiraEnSegundos: _ent(json['expires_in']),
        usuario: json['user'] is Map ? Usuario.desdeJson(_mapa(json['user'])) : null,
      );

  /// Token de acceso JWT (30 min de vida).
  final String acceso;

  /// Token de refresco opaco y rotatorio.
  final String refresco;

  /// Siempre `bearer` en el MVP.
  final String tipo;

  /// Segundos que faltan para que caduque [acceso].
  final int expiraEnSegundos;

  /// Usuario recién autenticado, cuando el servidor lo incluye.
  final Usuario? usuario;

  /// ¿El par es utilizable?
  bool get esValido => acceso.isNotEmpty;
}

/// Cuenta de la persona (`UserOut`): correo, rol, zona horaria e idioma.
class Usuario {
  const Usuario({
    required this.id,
    required this.correo,
    this.rol = RolUsuario.aprendiz,
    this.zonaHoraria = 'America/Santiago',
    this.idioma = 'es-CL',
    this.estaActiva = true,
    this.correoVerificadoEn,
    this.ultimoAccesoEn,
    this.creadoEn,
  });

  /// Lee el esquema `UserOut` de §7.1.
  factory Usuario.desdeJson(Map<String, dynamic> json) => Usuario(
        id: _txt(json['id']),
        correo: _txt(json['email']),
        rol: RolUsuario.desdeApi(json['role']),
        zonaHoraria: _txt(json['timezone'], 'America/Santiago'),
        idioma: _txt(json['locale'], 'es-CL'),
        estaActiva: _bol(json['is_active'], true),
        correoVerificadoEn: fechaHora(json['email_verified_at']),
        ultimoAccesoEn: fechaHora(json['last_login_at']),
        creadoEn: fechaHora(json['created_at']),
      );

  /// Identificador de la cuenta.
  final String id;

  /// Correo normalizado a minúsculas.
  final String correo;

  /// Rol de la cuenta.
  final RolUsuario rol;

  /// Zona IANA con la que el servidor calcula el día de la racha.
  final String zonaHoraria;

  /// Idioma de la interfaz (`es-CL`).
  final String idioma;

  /// `false` tras una baja lógica.
  final bool estaActiva;

  /// Verificación de correo, si la hubo.
  final DateTime? correoVerificadoEn;

  /// Último inicio de sesión exitoso.
  final DateTime? ultimoAccesoEn;

  /// Alta de la cuenta.
  final DateTime? creadoEn;
}

/// Preferencias de apariencia, notificaciones y contenido (`SettingsOut`, P21).
class Ajustes {
  const Ajustes({
    this.tema = PreferenciaTema.sistema,
    this.reducirMovimiento = false,
    this.sonidoActivado = true,
    this.hapticaActivada = true,
    this.pushActivado = false,
    this.tokenPush,
    this.modoRecordatorio = ModoRecordatorio.inteligente,
    this.horaRecordatorio,
    this.ultimaLlamadaActivada = false,
    this.silencioDesde,
    this.silencioHasta,
    this.avisarRutaLista = true,
    this.avisarRacha = true,
    this.avisarMisiones = false,
    this.idiomaContenido = 'es',
    this.zonaHoraria,
    this.idioma,
  });

  /// Lee `SettingsOut`; cualquier campo ausente cae al valor por defecto.
  factory Ajustes.desdeJson(Map<String, dynamic> json) => Ajustes(
        tema: PreferenciaTema.desdeApi(json['theme']),
        reducirMovimiento: _bol(json['reduce_motion']),
        sonidoActivado: _bol(json['sound_enabled'], true),
        hapticaActivada: _bol(json['haptics_enabled'], true),
        pushActivado: _bol(json['push_enabled']),
        tokenPush: _txtN(json['push_token']),
        modoRecordatorio: ModoRecordatorio.desdeApi(json['reminder_mode']),
        horaRecordatorio: HoraLocal.desdeTexto(json['reminder_time_local']),
        ultimaLlamadaActivada: _bol(json['last_call_enabled']),
        silencioDesde: HoraLocal.desdeTexto(json['quiet_hours_start']),
        silencioHasta: HoraLocal.desdeTexto(json['quiet_hours_end']),
        avisarRutaLista: _bol(json['notify_path_ready'], true),
        avisarRacha: _bol(json['notify_streak'], true),
        avisarMisiones: _bol(json['notify_missions']),
        idiomaContenido: _txt(json['content_language'], 'es'),
        zonaHoraria: _txtN(json['timezone']),
        idioma: _txtN(json['locale']),
      );

  /// Tema visual elegido.
  final PreferenciaTema tema;

  /// Accesibilidad: celebraciones en versión estática.
  final bool reducirMovimiento;

  /// Sonidos de recompensa.
  final bool sonidoActivado;

  /// Vibración.
  final bool hapticaActivada;

  /// Permiso de notificaciones push concedido.
  final bool pushActivado;

  /// Token FCM/APNs registrado.
  final String? tokenPush;

  /// Recordatorio inteligente, manual o apagado.
  final ModoRecordatorio modoRecordatorio;

  /// Hora fija del recordatorio cuando el modo es manual.
  final HoraLocal? horaRecordatorio;

  /// Segundo aviso de la noche (opt-in).
  final bool ultimaLlamadaActivada;

  /// Inicio de las horas de silencio.
  final HoraLocal? silencioDesde;

  /// Fin de las horas de silencio.
  final HoraLocal? silencioHasta;

  /// Aviso "tu ruta está lista".
  final bool avisarRutaLista;

  /// Avisos de racha.
  final bool avisarRacha;

  /// Aviso matutino de misiones.
  final bool avisarMisiones;

  /// Idioma en que se genera el contenido.
  final String idiomaContenido;

  /// Zona IANA del dispositivo, cuando el servidor la devuelve aquí.
  final String? zonaHoraria;

  /// Idioma de la interfaz, cuando el servidor lo devuelve aquí.
  final String? idioma;

  /// Cuerpo de `PUT /settings` con las claves literales del contrato.
  Map<String, dynamic> aJson() => <String, dynamic>{
        'theme': tema.api,
        'reduce_motion': reducirMovimiento,
        'sound_enabled': sonidoActivado,
        'haptics_enabled': hapticaActivada,
        'push_enabled': pushActivado,
        if (tokenPush != null) 'push_token': tokenPush,
        'reminder_mode': modoRecordatorio.api,
        'reminder_time_local': horaRecordatorio?.texto,
        'last_call_enabled': ultimaLlamadaActivada,
        if (silencioDesde != null) 'quiet_hours_start': silencioDesde!.texto,
        if (silencioHasta != null) 'quiet_hours_end': silencioHasta!.texto,
        'notify_path_ready': avisarRutaLista,
        'notify_streak': avisarRacha,
        'notify_missions': avisarMisiones,
        'content_language': idiomaContenido,
        if (zonaHoraria != null) 'timezone': zonaHoraria,
        if (idioma != null) 'locale': idioma,
      };

  /// Copia con los campos indicados sustituidos.
  Ajustes copiarCon({
    PreferenciaTema? tema,
    bool? reducirMovimiento,
    bool? sonidoActivado,
    bool? hapticaActivada,
    bool? pushActivado,
    String? tokenPush,
    ModoRecordatorio? modoRecordatorio,
    HoraLocal? horaRecordatorio,
    bool? ultimaLlamadaActivada,
    HoraLocal? silencioDesde,
    HoraLocal? silencioHasta,
    bool? avisarRutaLista,
    bool? avisarRacha,
    bool? avisarMisiones,
    String? idiomaContenido,
    String? zonaHoraria,
    String? idioma,
  }) =>
      Ajustes(
        tema: tema ?? this.tema,
        reducirMovimiento: reducirMovimiento ?? this.reducirMovimiento,
        sonidoActivado: sonidoActivado ?? this.sonidoActivado,
        hapticaActivada: hapticaActivada ?? this.hapticaActivada,
        pushActivado: pushActivado ?? this.pushActivado,
        tokenPush: tokenPush ?? this.tokenPush,
        modoRecordatorio: modoRecordatorio ?? this.modoRecordatorio,
        horaRecordatorio: horaRecordatorio ?? this.horaRecordatorio,
        ultimaLlamadaActivada: ultimaLlamadaActivada ?? this.ultimaLlamadaActivada,
        silencioDesde: silencioDesde ?? this.silencioDesde,
        silencioHasta: silencioHasta ?? this.silencioHasta,
        avisarRutaLista: avisarRutaLista ?? this.avisarRutaLista,
        avisarRacha: avisarRacha ?? this.avisarRacha,
        avisarMisiones: avisarMisiones ?? this.avisarMisiones,
        idiomaContenido: idiomaContenido ?? this.idiomaContenido,
        zonaHoraria: zonaHoraria ?? this.zonaHoraria,
        idioma: idioma ?? this.idioma,
      );
}

/// Estado de sesión y de onboarding (`MeOut` de `GET /auth/me`).
class Yo {
  const Yo({
    this.usuario,
    this.personaje,
    this.tienePersonaje = false,
    this.tieneRuta = false,
    this.ajustes,
  });

  /// Lee `{user, character, has_character, has_path, settings}`.
  factory Yo.desdeJson(Map<String, dynamic> json) => Yo(
        usuario: json['user'] is Map ? Usuario.desdeJson(_mapa(json['user'])) : null,
        personaje:
            json['character'] is Map ? Personaje.desdeJson(_mapa(json['character'])) : null,
        tienePersonaje: _bol(json['has_character'], json['character'] is Map),
        tieneRuta: _bol(json['has_path']),
        ajustes: json['settings'] is Map ? Ajustes.desdeJson(_mapa(json['settings'])) : null,
      );

  /// Cuenta autenticada.
  final Usuario? usuario;

  /// Personaje, si ya lo creó.
  final Personaje? personaje;

  /// ¿Ya pasó por la creación de personaje (P03)?
  final bool tienePersonaje;

  /// ¿Ya tiene al menos una Ruta?
  final bool tieneRuta;

  /// Preferencias vigentes.
  final Ajustes? ajustes;

  /// Siguiente paso del onboarding: `true` si aún falta crear el personaje.
  bool get faltaPersonaje => !tienePersonaje;

  /// `true` si ya hay personaje pero todavía ninguna Ruta.
  bool get faltaRuta => tienePersonaje && !tieneRuta;
}

// ---------------------------------------------------------------------------
// §7.2 Personaje, avatar e inventario
// ---------------------------------------------------------------------------

/// Personaje del usuario con nivel, XP y rango (`CharacterOut`).
class Personaje {
  const Personaje({
    required this.id,
    required this.nombre,
    this.arquetipo = Arquetipo.acero,
    this.nivel = 1,
    this.xpTotal = 0,
    this.tituloRango = 'Aprendiz',
    this.xpParaSiguiente = 0,
    this.porcentajeProgreso = 0,
    this.segundosEstudio = 0,
    this.saldoOro = 0,
    this.creadoEn,
    this.onboardadoEn,
    this.recompensas,
  });

  /// Lee `CharacterOut`; `rewards` solo llega al crear el personaje.
  factory Personaje.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> m =
        json['character'] is Map ? _mapa(json['character']) : json;
    return Personaje(
      id: _txt(m['id']),
      nombre: _txt(m['name']),
      arquetipo: Arquetipo.desdeApi(m['archetype']),
      nivel: _ent(m['level'], 1),
      xpTotal: _ent(m['xp_total']),
      tituloRango: _txt(m['rank_title'], 'Aprendiz'),
      xpParaSiguiente: _ent(m['xp_to_next']),
      porcentajeProgreso: _dec(m['progress_pct']),
      segundosEstudio: _ent(_alguna(m, <String>['total_study_seconds', 'study_seconds'])),
      saldoOro: _ent(_alguna(m, <String>['gold_balance', 'gold', 'balance'])),
      creadoEn: fechaHora(m['created_at']),
      onboardadoEn: fechaHora(m['onboarded_at']),
      recompensas: json['rewards'] is Map
          ? ReciboRecompensas.desdeJson(_mapa(json['rewards']))
          : null,
    );
  }

  /// Identificador del personaje.
  final String id;

  /// Nombre visible (3–20 caracteres).
  final String nombre;

  /// Orden elegida; sin efecto educativo.
  final Arquetipo arquetipo;

  /// Nivel global, calculado por el servidor.
  final int nivel;

  /// XP acumulado.
  final int xpTotal;

  /// Título del rango vigente.
  final String tituloRango;

  /// XP que falta para el siguiente nivel.
  final int xpParaSiguiente;

  /// Avance dentro del nivel actual, 0–100.
  final double porcentajeProgreso;

  /// Tiempo de estudio acumulado, en segundos.
  final int segundosEstudio;

  /// Saldo de oro, cuando el servidor lo adjunta.
  final int saldoOro;

  /// Alta del personaje.
  final DateTime? creadoEn;

  /// Fin de la creación de personaje.
  final DateTime? onboardadoEn;

  /// Recibo de la bolsa de bienvenida (solo en `POST /characters`).
  final ReciboRecompensas? recompensas;
}

/// Rasgos gratuitos del avatar: piel, rostro, orejas, cabello y trato.
class RasgosAvatar {
  const RasgosAvatar({
    this.tipoCuerpo = TipoCuerpo.neutro,
    this.tonoPiel = 'skin_03',
    this.rostro = 'face_01',
    this.orejas = 'round',
    this.cabello = 'hair_01',
    this.colorCabello = 'hair_black',
    this.formaTrato = FormaTrato.neutro,
    this.colorAcento,
    this.versionAssets = 1,
  });

  /// Lee el objeto `traits` de `AvatarOut`.
  factory RasgosAvatar.desdeJson(Map<String, dynamic> json) => RasgosAvatar(
        tipoCuerpo: TipoCuerpo.desdeApi(json['body_type']),
        tonoPiel: _txt(json['skin_tone'], 'skin_03'),
        rostro: _txt(json['face_id'], 'face_01'),
        orejas: _txt(json['ear_style'], 'round'),
        cabello: _txt(json['hair_style_id'], 'hair_01'),
        colorCabello: _txt(json['hair_color'], 'hair_black'),
        formaTrato: FormaTrato.desdeApi(json['address_form']),
        colorAcento: _txtN(json['accent_color']),
        versionAssets: _ent(json['asset_version'], 1),
      );

  /// Silueta; el MVP solo usa la neutra.
  final TipoCuerpo tipoCuerpo;

  /// Clave del tono de piel (6 tonos).
  final String tonoPiel;

  /// Rostro elegido (4 en el MVP).
  final String rostro;

  /// `round` o `pointed`.
  final String orejas;

  /// Estilo de cabello (8 en el MVP).
  final String cabello;

  /// Clave del color de cabello (10 en el MVP).
  final String colorCabello;

  /// Forma de tratamiento en los textos del juego.
  final FormaTrato formaTrato;

  /// Color de acento del perfil (`#RRGGBB`).
  final String? colorAcento;

  /// Versión del manifiesto de assets aplicada.
  final int versionAssets;

  /// Cuerpo de `PUT /avatar/traits`.
  Map<String, dynamic> aJson() => <String, dynamic>{
        'body_type': tipoCuerpo.api,
        'skin_tone': tonoPiel,
        'face_id': rostro,
        'ear_style': orejas,
        'hair_style_id': cabello,
        'hair_color': colorCabello,
        'address_form': formaTrato.api,
        if (colorAcento != null) 'accent_color': colorAcento,
      };

  /// Copia con los campos indicados sustituidos.
  RasgosAvatar copiarCon({
    TipoCuerpo? tipoCuerpo,
    String? tonoPiel,
    String? rostro,
    String? orejas,
    String? cabello,
    String? colorCabello,
    FormaTrato? formaTrato,
    String? colorAcento,
  }) =>
      RasgosAvatar(
        tipoCuerpo: tipoCuerpo ?? this.tipoCuerpo,
        tonoPiel: tonoPiel ?? this.tonoPiel,
        rostro: rostro ?? this.rostro,
        orejas: orejas ?? this.orejas,
        cabello: cabello ?? this.cabello,
        colorCabello: colorCabello ?? this.colorCabello,
        formaTrato: formaTrato ?? this.formaTrato,
        colorAcento: colorAcento ?? this.colorAcento,
        versionAssets: versionAssets,
      );
}

/// Una capa del manifiesto de render del avatar, ya ordenada por z.
class CapaAvatar {
  const CapaAvatar({
    required this.clave,
    this.ranura,
    this.assetKey = '',
    this.z = 0,
    this.desplazamientoX = 0,
    this.desplazamientoY = 0,
    this.tinte,
    this.itemId,
    this.itemUsuarioId,
    this.suprime = const <String>[],
  });

  /// Lee un elemento de `layers[]`.
  factory CapaAvatar.desdeJson(Map<String, dynamic> json) => CapaAvatar(
        clave: _txt(_alguna(json, <String>['key', 'layer_key', 'id'])),
        ranura: desdeClaveApiOpcional(RanuraItem.values, json['slot']),
        assetKey: _txt(_alguna(json, <String>['asset_key', 'asset', 'sprite'])),
        z: _ent(_alguna(json, <String>['z', 'z_index', 'order'])),
        desplazamientoX: _dec(_alguna(json, <String>['offset_x', 'dx'])),
        desplazamientoY: _dec(_alguna(json, <String>['offset_y', 'dy'])),
        tinte: _txtN(json['tint']),
        itemId: _txtN(json['item_id']),
        itemUsuarioId: _txtN(json['user_item_id']),
        suprime: _textos(json['suppresses_layers']),
      );

  /// Clave estable de la capa.
  final String clave;

  /// Ranura del avatar que ocupa, si la capa viene de un ítem.
  final RanuraItem? ranura;

  /// Clave del recurso gráfico a pintar.
  final String assetKey;

  /// Orden de apilado: menor se dibuja antes.
  final int z;

  /// Desplazamiento horizontal en unidades del lienzo.
  final double desplazamientoX;

  /// Desplazamiento vertical en unidades del lienzo.
  final double desplazamientoY;

  /// Color de tinte en `#RRGGBB`, si el manifiesto lo indica.
  final String? tinte;

  /// Ítem del catálogo que genera la capa.
  final String? itemId;

  /// Instancia poseída que genera la capa.
  final String? itemUsuarioId;

  /// Capas que esta oculta (por ejemplo, un yelmo que tapa el cabello).
  final List<String> suprime;
}

/// Avatar resuelto: rasgos, equipo y manifiesto de capas (`AvatarOut`).
class Avatar {
  const Avatar({
    this.rasgos = const RasgosAvatar(),
    this.arquetipo = Arquetipo.acero,
    this.equipo = const <String, String?>{},
    this.capas = const <CapaAvatar>[],
    this.etiquetaVersion,
  });

  /// Lee `{traits, archetype, equipment, layers[], etag}`.
  factory Avatar.desdeJson(Map<String, dynamic> json) {
    final List<CapaAvatar> capas = _lista(json['layers'], CapaAvatar.desdeJson)
      ..sort((CapaAvatar a, CapaAvatar b) => a.z.compareTo(b.z));
    return Avatar(
      rasgos: RasgosAvatar.desdeJson(_mapa(json['traits'])),
      arquetipo: Arquetipo.desdeApi(json['archetype']),
      equipo: _mapaTextos(json['equipment']),
      capas: List<CapaAvatar>.unmodifiable(capas),
      etiquetaVersion: _txtN(json['etag']),
    );
  }

  /// Rasgos gratuitos.
  final RasgosAvatar rasgos;

  /// Orden del personaje.
  final Arquetipo arquetipo;

  /// Mapa `ranura → user_item_id`; el valor nulo significa ranura vacía.
  final Map<String, String?> equipo;

  /// Capas ya ordenadas por z, listas para pintar.
  final List<CapaAvatar> capas;

  /// Versión del render, útil para invalidar caché de imagen.
  final String? etiquetaVersion;

  /// Instancia equipada en [ranura], o `null` si está vacía.
  String? equipadoEn(RanuraItem ranura) => equipo[ranura.api];

  /// Copia el mapa de equipo cambiando una sola ranura.
  Map<String, String?> equipoCon(RanuraItem ranura, String? itemUsuarioId) =>
      <String, String?>{...equipo, ranura.api: itemUsuarioId};
}

/// Condición de desbloqueo de un ítem, con su progreso explicado.
class Requisito {
  const Requisito({
    this.tipo = TipoRequisito.nivelMinimo,
    this.etiqueta = '',
    this.actual = 0,
    this.objetivo = 0,
    this.cumplido = false,
    this.grupo = 0,
    this.posicion = 0,
    this.areaSlug,
    this.areaConocimientoId,
    this.codigoLogro,
    this.tipoRacha,
  });

  /// Lee un elemento de `requirements[]` (`explain` del contrato).
  factory Requisito.desdeJson(Map<String, dynamic> json) => Requisito(
        tipo: TipoRequisito.desdeApi(
          _alguna(json, <String>['requirement_type', 'type']),
        ),
        etiqueta: _txt(_alguna(json, <String>['label', 'text', 'label_template'])),
        actual: _dec(_alguna(json, <String>['current', 'current_value', 'progress'])),
        objetivo: _dec(
          _alguna(json, <String>['target', 'target_value', 'target_count']),
        ),
        cumplido: _bol(_alguna(json, <String>['met', 'is_met', 'satisfied'])),
        grupo: _ent(json['group_index']),
        posicion: _ent(json['position']),
        areaSlug: _txtN(json['area_slug']),
        areaConocimientoId: _txtN(json['knowledge_area_id']),
        codigoLogro: _txtN(json['achievement_code']),
        tipoRacha: _txtN(json['streak_kind']),
      );

  /// Familia de la condición.
  final TipoRequisito tipo;

  /// Texto ya resuelto por el servidor ("Dominio de SQL: 44 / 80 %").
  final String etiqueta;

  /// Valor alcanzado por el usuario.
  final double actual;

  /// Valor exigido.
  final double objetivo;

  /// ¿Está cumplida?
  final bool cumplido;

  /// Grupo OR al que pertenece (se desbloquea si un grupo completo se cumple).
  final int grupo;

  /// Orden dentro del grupo.
  final int posicion;

  /// Slug del conocimiento exigido, o `self` en plantillas.
  final String? areaSlug;

  /// Conocimiento concreto exigido.
  final String? areaConocimientoId;

  /// Logro exigido.
  final String? codigoLogro;

  /// `current` o `best` para las condiciones de racha.
  final String? tipoRacha;

  /// Avance 0–1 hacia la condición; 1 si ya está cumplida.
  double get fraccion {
    if (cumplido) return 1;
    if (objetivo <= 0) return 0;
    final double f = actual / objetivo;
    return f < 0 ? 0 : (f > 1 ? 1 : f);
  }
}

/// Ítem del catálogo: identidad, rareza, ranura y manifiesto de render.
class Item {
  const Item({
    required this.id,
    this.codigo = '',
    this.nombre = '',
    this.descripcion,
    this.ranura = RanuraItem.accesorio,
    this.rareza = RarezaItem.comun,
    this.origen = OrigenItem.tienda,
    this.visibilidad = VisibilidadItem.publico,
    this.iconoKey,
    this.areaConocimientoId,
    this.nombreConocimiento,
    this.capas = const <CapaAvatar>[],
    this.esPlantilla = false,
    this.disponibleDesde,
    this.disponibleHasta,
  });

  /// Lee el esquema de ítem del catálogo (`items`).
  factory Item.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> manifiesto = _mapa(json['render_manifest']);
    return Item(
      id: _txt(_alguna(json, <String>['id', 'item_id'])),
      codigo: _txt(_alguna(json, <String>['code', 'item_code'])),
      nombre: _txt(json['name']),
      descripcion: _txtN(json['description']),
      ranura: RanuraItem.desdeApi(json['slot']),
      rareza: RarezaItem.desdeApi(json['rarity']),
      origen: OrigenItem.desdeApi(json['origin']),
      visibilidad: VisibilidadItem.desdeApi(json['visibility']),
      iconoKey: _txtN(json['icon_key']),
      areaConocimientoId: _txtN(json['knowledge_area_id']),
      nombreConocimiento: _txtN(
        _alguna(json, <String>['knowledge_area_name', 'area_name']),
      ),
      capas: _lista(
        _alguna(json, <String>['layers']) ?? manifiesto['layers'],
        CapaAvatar.desdeJson,
      ),
      esPlantilla: _bol(json['is_template']),
      disponibleDesde: fechaHora(json['available_from']),
      disponibleHasta: fechaHora(json['available_to']),
    );
  }

  /// Identificador del ítem del catálogo.
  final String id;

  /// Slug estable (`espada_del_sql`).
  final String codigo;

  /// Nombre visible.
  final String nombre;

  /// Lore de una o dos frases.
  final String? descripcion;

  /// Ranura del avatar que ocupa.
  final RanuraItem ranura;

  /// Rareza; el color sale de `Rareza` en los tokens.
  final RarezaItem rareza;

  /// Origen principal: Mercado, logro, racha o conocimiento.
  final OrigenItem origen;

  /// Quién lo ve aunque esté bloqueado.
  final VisibilidadItem visibilidad;

  /// Icono dedicado cuando el recorte no lee bien.
  final String? iconoKey;

  /// Conocimiento que tematiza el ítem derivado.
  final String? areaConocimientoId;

  /// Nombre del conocimiento asociado, si el servidor lo adjunta.
  final String? nombreConocimiento;

  /// Capas de render del ítem.
  final List<CapaAvatar> capas;

  /// `true` si es una plantilla derivable, no equipable.
  final bool esPlantilla;

  /// Inicio de la ventana de disponibilidad.
  final DateTime? disponibleDesde;

  /// Fin de la ventana de disponibilidad.
  final DateTime? disponibleHasta;

  /// ¿Se gana aprendiendo en lugar de comprarse?
  bool get seGanaAprendiendo => origen == OrigenItem.conocimiento;
}

/// Fila del Vestidor (`InventoryItemOut`): ítem, posesión y requisitos (P16).
class ItemInventario {
  const ItemInventario({
    required this.item,
    this.itemUsuarioId,
    this.poseido = false,
    this.esNuevo = false,
    this.equipado = false,
    this.requisitos = const <Requisito>[],
    this.adquiridoEn,
    this.motivoDesbloqueo,
    this.puedeEquipar = false,
  });

  /// Lee `{item, owned, is_new, equipped, requirements[]}`.
  factory ItemInventario.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> crudo = json['item'] is Map ? _mapa(json['item']) : json;
    final bool poseido = _bol(_alguna(json, <String>['owned', 'is_owned']));
    return ItemInventario(
      item: Item.desdeJson(crudo),
      itemUsuarioId: _txtN(json['user_item_id']),
      poseido: poseido,
      esNuevo: _bol(json['is_new']),
      equipado: _bol(_alguna(json, <String>['equipped', 'is_equipped'])),
      requisitos: _lista(json['requirements'], Requisito.desdeJson),
      adquiridoEn: fechaHora(json['acquired_at']),
      motivoDesbloqueo: _txtN(json['unlock_reason']),
      puedeEquipar: _bol(json['can_equip'], poseido),
    );
  }

  /// Ítem del catálogo.
  final Item item;

  /// Instancia poseída, si el usuario ya lo tiene.
  final String? itemUsuarioId;

  /// ¿Está en el inventario?
  final bool poseido;

  /// Insignia "nuevo" hasta abrir la ficha.
  final bool esNuevo;

  /// ¿Está equipado ahora mismo?
  final bool equipado;

  /// Condiciones de desbloqueo con su progreso.
  final List<Requisito> requisitos;

  /// Fecha de adquisición.
  final DateTime? adquiridoEn;

  /// Frase que explica cómo se consiguió o se consigue.
  final String? motivoDesbloqueo;

  /// ¿Se puede equipar ya?
  final bool puedeEquipar;

  /// ¿Se muestra en silueta con candado?
  bool get estaBloqueado => !poseido;

  /// Requisitos que todavía faltan.
  List<Requisito> get requisitosPendientes =>
      requisitos.where((Requisito r) => !r.cumplido).toList(growable: false);
}

/// Ficha completa de un ítem con lore, requisitos y precio (`ItemDetailOut`).
class DetalleItem {
  const DetalleItem({
    required this.inventario,
    this.precio,
    this.moneda = 'gold',
    this.nivelMinimo = 1,
    this.anuncioId,
    this.puedeComprar = false,
    this.saldoOro = 0,
  });

  /// Lee `ItemDetailOut`, que envuelve la fila de inventario y su listado.
  factory DetalleItem.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> listado = _mapa(json['listing']);
    return DetalleItem(
      inventario: ItemInventario.desdeJson(json),
      precio: _entN(_alguna(json, <String>['price']) ?? listado['price']),
      moneda: _txt(_alguna(json, <String>['currency']) ?? listado['currency'], 'gold'),
      nivelMinimo: _ent(
        _alguna(json, <String>['min_level']) ?? listado['min_level'],
        1,
      ),
      anuncioId: _txtN(_alguna(json, <String>['listing_id']) ?? listado['id']),
      // Misma historia que en el Mercado: `ItemDetailOut` trae `owned` y
      // `locked`, nunca `can_buy`.
      puedeComprar: Anuncio._autorizaComprar(<String, dynamic>{
        ...listado,
        'owned': _alguna(json, <String>['owned', 'is_owned']),
        'locked': _alguna(json, <String>['locked', 'is_locked']),
      }),
      saldoOro: _ent(_alguna(json, <String>['balance', 'gold_balance'])),
    );
  }

  /// Ítem con su estado de posesión y sus requisitos.
  final ItemInventario inventario;

  /// Precio vigente en el Mercado, o `null` si no se vende.
  final int? precio;

  /// Moneda del precio (solo `gold` en el MVP).
  final String moneda;

  /// Nivel mínimo para comprarlo.
  final int nivelMinimo;

  /// Listado del Mercado asociado.
  final String? anuncioId;

  /// ¿El servidor autoriza la compra ahora?
  final bool puedeComprar;

  /// Saldo de oro del usuario en el momento de consultar.
  final int saldoOro;

  /// El mismo detalle, completado con lo que el Mercado ya sabe.
  ///
  /// `ItemDetailOut` no trae precio, listado ni saldo: son datos de la tienda,
  /// no del ítem. Sin esto la ficha abierta desde el Mercado no encontraba
  /// `anuncioId` y ofrecía un botón de "Entendido" en vez del de comprar, así
  /// que no había ninguna pantalla desde la que gastar una moneda.
  DetalleItem conAnuncio(Anuncio anuncio, {int saldo = 0}) => DetalleItem(
        inventario: inventario,
        precio: anuncio.precio,
        moneda: anuncio.moneda,
        nivelMinimo: anuncio.nivelMinimo,
        anuncioId: anuncio.id,
        puedeComprar: anuncio.puedeComprar,
        saldoOro: saldo,
      );

  /// Atajo al ítem del catálogo.
  Item get item => inventario.item;

  /// Oro que falta para poder comprarlo; 0 si alcanza o no se vende.
  int get oroFaltante {
    final int? p = precio;
    if (p == null || saldoOro >= p) return 0;
    return p - saldoOro;
  }
}

// ---------------------------------------------------------------------------
// §7.3 Tienda y monedero
// ---------------------------------------------------------------------------

/// Oferta del Mercado: ítem, precio y si se puede comprar ya (`ShopListingOut`).
class Anuncio {
  const Anuncio({
    required this.id,
    required this.item,
    this.precio = 0,
    this.moneda = 'gold',
    this.nivelMinimo = 1,
    this.destacado = false,
    this.ordenDestacado,
    this.poseido = false,
    this.bloqueado = false,
    this.puedeComprar = false,
    this.puedePagar = false,
    this.motivoBloqueo,
    this.requisitos = const <Requisito>[],
  });

  /// Lee un elemento de `listings[]`, `featured[]` o `knowledge_items[]`.
  factory Anuncio.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> crudo = json['item'] is Map ? _mapa(json['item']) : json;
    return Anuncio(
      id: _txt(_alguna(json, <String>['id', 'listing_id'])),
      item: Item.desdeJson(crudo),
      precio: _ent(json['price']),
      moneda: _txt(json['currency'], 'gold'),
      nivelMinimo: _ent(json['min_level'], 1),
      destacado: _bol(json['is_featured']),
      ordenDestacado: _entN(json['featured_order']),
      poseido: _bol(_alguna(json, <String>['owned', 'is_owned'])),
      bloqueado: _bol(_alguna(json, <String>['locked', 'is_locked'])),
      puedeComprar: _autorizaComprar(json),
      puedePagar: _bol(_alguna(json, <String>['can_afford', 'has_enough_gold'])),
      motivoBloqueo: _txtN(
        _alguna(json, <String>['unlock_reason', 'locked_reason', 'lock_reason']),
      ),
      requisitos: _lista(json['requirements'], Requisito.desdeJson),
    );
  }

  /// ¿El Reino autoriza esta compra?
  ///
  /// `ShopListingOut` **no** trae `can_buy`: trae las tres piezas con las que
  /// se decide (`owned`, `locked`, `can_afford`). Leer un campo que el servidor
  /// nunca emite dejaba el permiso en falso siempre, así que el botón de
  /// comprar no se activaba para nadie y no se podía gastar una sola moneda.
  ///
  /// Si un día el servidor empieza a mandar el veredicto ya resuelto, manda ese.
  static bool _autorizaComprar(Map<String, dynamic> json) {
    final Object? explicito = _alguna(json, <String>['can_buy', 'can_purchase']);
    if (explicito != null) return _bol(explicito);
    final bool poseido = _bol(_alguna(json, <String>['owned', 'is_owned']));
    final bool bloqueado = _bol(_alguna(json, <String>['locked', 'is_locked']));
    final bool alcanza = _bol(_alguna(json, <String>['can_afford', 'has_enough_gold']));
    return !poseido && !bloqueado && alcanza;
  }

  /// Identificador del listado (lo pide `POST /shop/purchase`).
  final String id;

  /// Ítem ofertado.
  final Item item;

  /// Precio vigente en oro, tal como lo fija el servidor.
  final int precio;

  /// Moneda (solo `gold` activa en el MVP).
  final String moneda;

  /// Nivel mínimo para comprarlo.
  final int nivelMinimo;

  /// ¿Aparece en la franja de destacados?
  final bool destacado;

  /// Orden entre los destacados.
  final int? ordenDestacado;

  /// ¿El usuario ya lo tiene?
  final bool poseido;

  /// ¿Le falta algún requisito (nivel, logro, dominio) para poder comprarlo?
  final bool bloqueado;

  /// ¿El servidor autoriza la compra?
  final bool puedeComprar;

  /// ¿Le alcanza el oro?
  final bool puedePagar;

  /// Frase de por qué está bloqueado ("Alcanza el nivel 5").
  final String? motivoBloqueo;

  /// Requisitos pendientes de este ítem.
  final List<Requisito> requisitos;

  /// ¿Es de la sección "Se ganan aprendiendo"?
  bool get seGanaAprendiendo => item.seGanaAprendiendo;

  /// El mismo anuncio con el Mercado todavía cerrado.
  ///
  /// El servidor rechaza cualquier compra por debajo de `shop.unlock_level`, así
  /// que ofrecerla sería prometer algo que no se puede cumplir.
  Anuncio conMercadoCerrado() => Anuncio(
        id: id,
        item: item,
        precio: precio,
        moneda: moneda,
        nivelMinimo: nivelMinimo,
        destacado: destacado,
        ordenDestacado: ordenDestacado,
        poseido: poseido,
        bloqueado: true,
        puedeComprar: false,
        puedePagar: puedePagar,
        motivoBloqueo: motivoBloqueo ?? 'El Mercado abre más adelante.',
        requisitos: requisitos,
      );
}

/// Catálogo del Mercado con saldo y destacados (`ShopOut`, P15).
class Tienda {
  const Tienda({
    this.saldo = 0,
    this.destacados = const <Anuncio>[],
    this.anuncios = const <Anuncio>[],
    this.itemsDeConocimiento = const <Anuncio>[],
    this.rarezasDesbloqueadas = const <String>[],
    this.abierta = true,
    this.nivelDeApertura = 1,
  });

  /// Lee `{balance, featured[], listings[], knowledge_items[]}`.
  ///
  /// `shop_unlocked` y `unlock_level` viven en la tienda, no en cada anuncio, y
  /// el servidor los comprueba al comprar. Sin leerlos aquí, la interfaz ofrecía
  /// objetos comprables con el Mercado todavía cerrado.
  factory Tienda.desdeJson(Map<String, dynamic> json) {
    final bool abierta = _alguna(json, <String>['shop_unlocked']) == null
        ? true
        : _bol(json['shop_unlocked']);
    return Tienda(
      saldo: _ent(_alguna(json, <String>['balance', 'gold_balance'])),
      destacados: _anuncios(json['featured'], abierta: abierta),
      anuncios: _anuncios(json['listings'], abierta: abierta),
      itemsDeConocimiento: _anuncios(json['knowledge_items'], abierta: abierta),
      rarezasDesbloqueadas: _textos(json['unlocked_rarities']),
      abierta: abierta,
      nivelDeApertura: _ent(_alguna(json, <String>['unlock_level']), 1),
    );
  }

  static List<Anuncio> _anuncios(Object? crudo, {required bool abierta}) {
    final List<Anuncio> salida = _lista(crudo, Anuncio.desdeJson);
    if (abierta) return salida;
    return <Anuncio>[
      for (final Anuncio a in salida) a.conMercadoCerrado(),
    ];
  }

  /// Saldo de oro del usuario.
  final int saldo;

  /// Ofertas destacadas (2–4 a la vez).
  final List<Anuncio> destacados;

  /// Catálogo activo.
  final List<Anuncio> anuncios;

  /// Ítems que no se compran: se ganan aprendiendo.
  final List<Anuncio> itemsDeConocimiento;

  /// Rarezas que el nivel del usuario ya habilita.
  final List<String> rarezasDesbloqueadas;

  /// ¿El Mercado ya está abierto para este héroe?
  final bool abierta;

  /// Nivel en el que se abre el Mercado.
  final int nivelDeApertura;

  /// Ofertas de una ranura concreta.
  List<Anuncio> porRanura(RanuraItem ranura) =>
      anuncios.where((Anuncio a) => a.item.ranura == ranura).toList(growable: false);

  /// Ofertas que el usuario puede pagar y comprar ahora.
  List<Anuncio> get alcanzables => anuncios
      .where((Anuncio a) => a.puedeComprar && a.puedePagar && !a.poseido)
      .toList(growable: false);
}

/// Orden de compra ya ejecutada por el servidor (`purchases`).
class OrdenCompra {
  const OrdenCompra({
    required this.id,
    this.anuncioId = '',
    this.itemId = '',
    this.precio = 0,
    this.moneda = 'gold',
    this.estado = EstadoCompra.completada,
    this.itemUsuarioId,
    this.creadaEn,
    this.revertidaEn,
  });

  /// Lee el objeto `purchase` de `PurchaseOut`.
  factory OrdenCompra.desdeJson(Map<String, dynamic> json) => OrdenCompra(
        id: _txt(_alguna(json, <String>['id', 'purchase_id'])),
        anuncioId: _txt(json['listing_id']),
        itemId: _txt(json['item_id']),
        precio: _ent(json['price']),
        moneda: _txt(json['currency'], 'gold'),
        estado: EstadoCompra.desdeApi(json['status']),
        itemUsuarioId: _txtN(json['user_item_id']),
        creadaEn: fechaHora(json['created_at']),
        revertidaEn: fechaHora(json['reversed_at']),
      );

  /// Identificador de la orden (lo pide "Deshacer").
  final String id;

  /// Listado comprado.
  final String anuncioId;

  /// Ítem adquirido.
  final String itemId;

  /// Precio cobrado por el servidor.
  final int precio;

  /// Moneda del cobro.
  final String moneda;

  /// Completada o revertida.
  final EstadoCompra estado;

  /// Instancia entregada al inventario.
  final String? itemUsuarioId;

  /// Momento de la compra.
  final DateTime? creadaEn;

  /// Momento de la reversión, si la hubo.
  final DateTime? revertidaEn;

  /// ¿Sigue vigente?
  bool get estaVigente => estado == EstadoCompra.completada && revertidaEn == null;
}

/// Resultado de comprar o de deshacer una compra (`PurchaseOut`).
class Compra {
  const Compra({
    required this.orden,
    this.itemUsuario,
    this.saldoDespues = 0,
    this.capasAvatar = const <CapaAvatar>[],
  });

  /// Lee `{purchase, user_item, balance_after, avatar_layers}`.
  factory Compra.desdeJson(Map<String, dynamic> json) {
    final List<CapaAvatar> capas = _lista(json['avatar_layers'], CapaAvatar.desdeJson)
      ..sort((CapaAvatar a, CapaAvatar b) => a.z.compareTo(b.z));
    return Compra(
      orden: OrdenCompra.desdeJson(
        json['purchase'] is Map ? _mapa(json['purchase']) : json,
      ),
      itemUsuario: json['user_item'] is Map
          ? ItemInventario.desdeJson(_mapa(json['user_item']))
          : null,
      saldoDespues: _ent(_alguna(json, <String>['balance_after', 'balance'])),
      capasAvatar: List<CapaAvatar>.unmodifiable(capas),
    );
  }

  /// Orden ejecutada.
  final OrdenCompra orden;

  /// Instancia entregada, lista para el Vestidor.
  final ItemInventario? itemUsuario;

  /// Saldo de oro tras la operación, calculado por el servidor.
  final int saldoDespues;

  /// Manifiesto de capas con el ítem ya puesto, para la vista previa.
  final List<CapaAvatar> capasAvatar;
}

/// Movimiento del ledger de oro (`GoldTransactionOut`).
class MovimientoOro {
  const MovimientoOro({
    required this.id,
    this.sentido = SentidoMovimiento.ingreso,
    this.cantidad = 0,
    this.saldoDespues = 0,
    this.motivo = '',
    this.origen,
    this.destino,
    this.ocurridoEn,
    this.fechaLocal,
  });

  /// Lee una fila de `gold_transactions`.
  factory MovimientoOro.desdeJson(Map<String, dynamic> json) => MovimientoOro(
        id: _txt(json['id']),
        sentido: SentidoMovimiento.desdeApi(json['direction']),
        cantidad: _ent(json['amount']),
        saldoDespues: _ent(json['balance_after']),
        motivo: _txt(json['reason_code']),
        origen: _txtN(json['source']),
        destino: _txtN(json['sink']),
        ocurridoEn: fechaHora(_alguna(json, <String>['created_at', 'occurred_at'])),
        fechaLocal: fechaDia(json['local_date']),
      );

  /// Identificador del movimiento.
  final String id;

  /// Ingreso o gasto.
  final SentidoMovimiento sentido;

  /// Importe, siempre positivo.
  final int cantidad;

  /// Saldo tras la transacción, calculado por el servidor.
  final int saldoDespues;

  /// Código estable del motivo (`first_completion`, `purchase`…).
  final String motivo;

  /// Dimensión de origen en los ingresos.
  final String? origen;

  /// Dimensión de destino en los gastos.
  final String? destino;

  /// Momento del movimiento.
  final DateTime? ocurridoEn;

  /// Día local al que se imputa.
  final DateTime? fechaLocal;

  /// ¿Suma oro?
  bool get esIngreso => sentido == SentidoMovimiento.ingreso;
}

/// Saldo y últimos movimientos de oro (`WalletOut`).
class Monedero {
  const Monedero({
    required this.movimientos,
    this.saldo = 0,
    this.totalGanado = 0,
    this.totalGastado = 0,
  });

  /// Lee `{balance, lifetime_earned, lifetime_spent, transactions}`.
  factory Monedero.desdeJson(Map<String, dynamic> json) => Monedero(
        saldo: _ent(json['balance']),
        totalGanado: _ent(json['lifetime_earned']),
        totalGastado: _ent(json['lifetime_spent']),
        movimientos: Pagina<MovimientoOro>.desdeJson(
          json['transactions'],
          MovimientoOro.desdeJson,
        ),
      );

  /// Saldo vigente.
  final int saldo;

  /// Oro ganado de por vida.
  final int totalGanado;

  /// Oro gastado de por vida.
  final int totalGastado;

  /// Página de movimientos recientes.
  final Pagina<MovimientoOro> movimientos;
}

// ---------------------------------------------------------------------------
// §7.4 Conocimientos y mundo
// ---------------------------------------------------------------------------

/// Cómo se compone el dominio de un tema o de un conocimiento, en palabras.
class ExplicacionDominio {
  const ExplicacionDominio({
    this.texto = '',
    this.practica,
    this.cobertura,
    this.decaimiento,
    this.evidencias = 0,
    this.ultimaEvidenciaEn,
  });

  /// Lee `mastery_explain` (o `explain`) del detalle de conocimiento.
  factory ExplicacionDominio.desdeJson(Map<String, dynamic> json) =>
      ExplicacionDominio(
        texto: _txt(_alguna(json, <String>['text', 'summary', 'label'])),
        practica: _decN(_alguna(json, <String>['practice_pct', 'practice'])),
        cobertura: _decN(_alguna(json, <String>['coverage_pct', 'coverage'])),
        decaimiento: _decN(_alguna(json, <String>['decay_pct', 'decay'])),
        evidencias: _ent(_alguna(json, <String>['evidence_count', 'evidences'])),
        ultimaEvidenciaEn: fechaHora(json['last_evidence_at']),
      );

  /// Frase ya redactada por el servidor.
  final String texto;

  /// Componente de práctica (aciertos ponderados), 0–100.
  final double? practica;

  /// Componente de cobertura (lecciones completadas), 0–100.
  final double? cobertura;

  /// Pérdida aplicada por la curva de olvido, 0–100.
  final double? decaimiento;

  /// Número de evidencias consideradas.
  final int evidencias;

  /// Última respuesta que alimentó el dominio.
  final DateTime? ultimaEvidenciaEn;

  /// ¿Hay algo que mostrar?
  bool get tieneDetalle =>
      texto.isNotEmpty || practica != null || cobertura != null || decaimiento != null;
}

/// Conocimiento del catálogo con el progreso del usuario (`KnowledgeAreaOut`).
class AreaConocimiento {
  const AreaConocimiento({
    required this.id,
    this.slug = '',
    this.nombre = '',
    this.nombreCorto = '',
    this.categoria = CategoriaConocimiento.otro,
    this.descripcion,
    this.iconoKey,
    this.colorAcento,
    this.esCanonica = false,
    this.nivel = 1,
    this.xp = 0,
    this.tituloRango,
    this.dominio = 0,
    this.segundosEstudio = 0,
    this.estado = EstadoDominio.sinEvidencia,
    this.ultimaActividadEn,
  });

  /// Lee `KnowledgeAreaOut`; el progreso puede venir plano o dentro de
  /// `progress`, y el catálogo plano o dentro de `area`.
  factory AreaConocimiento.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> area = json['area'] is Map ? _mapa(json['area']) : json;
    final Map<String, dynamic> avance =
        json['progress'] is Map ? _mapa(json['progress']) : json;
    return AreaConocimiento(
      id: _txt(_alguna(area, <String>['id', 'knowledge_area_id'])),
      slug: _txt(area['slug']),
      nombre: _txt(area['name']),
      nombreCorto: _txt(area['short_name'], _txt(area['name'])),
      categoria: CategoriaConocimiento.desdeApi(area['category']),
      descripcion: _txtN(area['description']),
      iconoKey: _txtN(area['icon_key']),
      colorAcento: _txtN(area['accent_color']),
      esCanonica: _bol(area['is_canonical']),
      nivel: _ent(avance['level'], 1),
      xp: _ent(avance['xp']),
      tituloRango: _txtN(avance['rank_title']),
      dominio: _dec(_alguna(avance, <String>['mastery', 'mastery_pct'])),
      segundosEstudio: _ent(avance['study_seconds']),
      estado: EstadoDominio.desdeApi(avance['status']),
      ultimaActividadEn: fechaHora(avance['last_activity_at']),
    );
  }

  /// Identificador del conocimiento.
  final String id;

  /// Slug canónico estable (`sql`).
  final String slug;

  /// Nombre visible ("SQL").
  final String nombre;

  /// Nombre corto para las plantillas de ítems.
  final String nombreCorto;

  /// Categoría que tinta los ítems derivados.
  final CategoriaConocimiento categoria;

  /// Descripción breve.
  final String? descripcion;

  /// Clave del emblema.
  final String? iconoKey;

  /// Color de la categoría (`#RRGGBB`).
  final String? colorAcento;

  /// `true` en la taxonomía semilla curada.
  final bool esCanonica;

  /// Nivel del usuario en este conocimiento.
  final int nivel;

  /// XP acumulado en este conocimiento.
  final int xp;

  /// Prefijo del título ("Competente en").
  final String? tituloRango;

  /// Dominio 0–100 calculado por el servidor.
  final double dominio;

  /// Tiempo dedicado, en segundos.
  final int segundosEstudio;

  /// Estado de dominio.
  final EstadoDominio estado;

  /// Última actividad del área.
  final DateTime? ultimaActividadEn;

  /// ¿El usuario ya tiene progreso aquí?
  bool get tieneProgreso => xp > 0 || segundosEstudio > 0 || dominio > 0;
}

/// Territorio del mapa simplificado (`TerritoryOut`, P22).
class Territorio {
  const Territorio({
    required this.id,
    this.areaConocimientoId = '',
    this.nombre = '',
    this.iconoKey,
    this.descripcion,
    this.estado = EstadoTerritorio.bruma,
    this.dominio = 0,
    this.nombreConocimiento,
    this.colorAcento,
    this.zonasTotales = 0,
    this.zonasDesbloqueadas = 0,
    this.rutaId,
  });

  /// Lee `TerritoryOut`.
  factory Territorio.desdeJson(Map<String, dynamic> json) => Territorio(
        id: _txt(_alguna(json, <String>['id', 'territory_id'])),
        areaConocimientoId: _txt(json['knowledge_area_id']),
        nombre: _txt(json['name']),
        iconoKey: _txtN(_alguna(json, <String>['icon_hint', 'icon_key'])),
        descripcion: _txtN(json['description']),
        estado: EstadoTerritorio.desdeApi(json['status']),
        dominio: _dec(_alguna(json, <String>['mastery', 'mastery_pct'])),
        nombreConocimiento: _txtN(
          _alguna(json, <String>['knowledge_area_name', 'area_name']),
        ),
        colorAcento: _txtN(json['accent_color']),
        zonasTotales: _ent(_alguna(json, <String>['zones_total', 'modules_total'])),
        zonasDesbloqueadas: _ent(
          _alguna(json, <String>['zones_unlocked', 'modules_unlocked']),
        ),
        rutaId: _txtN(_alguna(json, <String>['learning_path_id', 'path_id'])),
      );

  /// Identificador del territorio.
  final String id;

  /// Conocimiento que representa.
  final String areaConocimientoId;

  /// Nombre narrativo ("Castillo de las Consultas").
  final String nombre;

  /// Pista visual del emblema (`castle`, `forest`).
  final String? iconoKey;

  /// Texto de sabor.
  final String? descripcion;

  /// Bruma, explorado o dominado.
  final EstadoTerritorio estado;

  /// Dominio del conocimiento, 0–100.
  final double dominio;

  /// Nombre del conocimiento.
  final String? nombreConocimiento;

  /// Color de acento del territorio.
  final String? colorAcento;

  /// Zonas (módulos) totales.
  final int zonasTotales;

  /// Zonas ya desbloqueadas.
  final int zonasDesbloqueadas;

  /// Ruta principal asociada, si la hay.
  final String? rutaId;
}

/// Detalle de un conocimiento con módulos, temas débiles y explicación (§7.4).
class DetalleAreaConocimiento {
  const DetalleAreaConocimiento({
    required this.area,
    this.explicacionDominio = const ExplicacionDominio(),
    this.territorio,
    this.modulos = const <ModuloRuta>[],
    this.temasDebiles = const <Tema>[],
    this.rutas = const <ResumenRuta>[],
    this.modulosDominados = 0,
    this.temasDominados = 0,
    this.rutasCompletadas = 0,
  });

  /// Lee `KnowledgeAreaDetailOut`.
  factory DetalleAreaConocimiento.desdeJson(Map<String, dynamic> json) =>
      DetalleAreaConocimiento(
        area: AreaConocimiento.desdeJson(json),
        explicacionDominio: ExplicacionDominio.desdeJson(
          _mapa(_alguna(json, <String>['mastery_explain', 'explain'])),
        ),
        territorio: json['territory'] is Map
            ? Territorio.desdeJson(_mapa(json['territory']))
            : null,
        modulos: _lista(json['modules'], ModuloRuta.desdeJson),
        temasDebiles: _lista(json['weak_topics'], Tema.desdeJson),
        rutas: _lista(json['paths'], ResumenRuta.desdeJson),
        modulosDominados: _ent(json['modules_mastered']),
        temasDominados: _ent(json['topics_mastered']),
        rutasCompletadas: _ent(json['paths_completed']),
      );

  /// Conocimiento con su progreso.
  final AreaConocimiento area;

  /// De qué se compone el dominio.
  final ExplicacionDominio explicacionDominio;

  /// Territorio que lo representa en el mapa.
  final Territorio? territorio;

  /// Módulos del conocimiento con su avance.
  final List<ModuloRuta> modulos;

  /// Temas por debajo del umbral que conviene repasar.
  final List<Tema> temasDebiles;

  /// Rutas del usuario en este conocimiento.
  final List<ResumenRuta> rutas;

  /// Módulos dominados.
  final int modulosDominados;

  /// Temas dominados.
  final int temasDominados;

  /// Rutas completadas.
  final int rutasCompletadas;
}

// ---------------------------------------------------------------------------
// §7.5 Rutas de aprendizaje y material
// ---------------------------------------------------------------------------

/// Aviso de cobertura devuelto por la Fase A ("este tema no está en tu material").
class AvisoCobertura {
  const AvisoCobertura({
    this.nivel = NivelCobertura.completa,
    this.mensaje = '',
    this.temaId,
    this.tituloTema,
  });

  /// Lee un elemento de `coverage_notes`.
  factory AvisoCobertura.desdeJson(Map<String, dynamic> json) => AvisoCobertura(
        nivel: NivelCobertura.desdeApi(
          _alguna(json, <String>['coverage', 'level', 'status']),
        ),
        mensaje: _txt(_alguna(json, <String>['message', 'note', 'text'])),
        temaId: _txtN(json['topic_id']),
        tituloTema: _txtN(_alguna(json, <String>['topic_title', 'title'])),
      );

  /// Cobertura del material para el tema señalado.
  final NivelCobertura nivel;

  /// Texto ya redactado por el servidor.
  final String mensaje;

  /// Tema afectado, si el aviso es de un tema concreto.
  final String? temaId;

  /// Título del tema afectado.
  final String? tituloTema;
}

/// Ruta en una lista: "Mis rutas" y "Rutas del Reino" (`PathSummaryOut`, P22).
class ResumenRuta {
  const ResumenRuta({
    required this.id,
    this.titulo = '',
    this.objetivo,
    this.resumen,
    this.areaConocimientoId = '',
    this.nombreConocimiento,
    this.colorAcento,
    this.iconoKey,
    this.nivelDeclarado = NivelDeclarado.principiante,
    this.modoFuente = ModoFuente.conFuente,
    this.origen = OrigenRuta.propia,
    this.estado = EstadoRuta.borrador,
    this.politicaCobertura = PoliticaCobertura.conocimientoDelModelo,
    this.modulos = 0,
    this.minutosEstimados,
    this.estadoProgreso = EstadoProgreso.sinEmpezar,
    this.modulosCompletados = 0,
    this.leccionesTotales = 0,
    this.leccionesCompletadas = 0,
    this.porcentajeAvance = 0,
    this.dominio = 0,
    this.moduloActualId,
    this.leccionActualId,
    this.esPublica = false,
    this.creadaEn,
    this.confirmadaEn,
    this.completadaEn,
    this.archivadaEn,
    this.ultimaActividadEn,
  });

  /// Lee `PathSummaryOut`; acepta la ruta plana o anidada en `path`, y el
  /// avance plano o anidado en `progress`.
  factory ResumenRuta.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> r = json['path'] is Map ? _mapa(json['path']) : json;
    final Map<String, dynamic> p =
        json['progress'] is Map ? _mapa(json['progress']) : json;
    return ResumenRuta(
      id: _txt(_alguna(r, <String>['id', 'learning_path_id', 'path_id'])),
      titulo: _txt(r['title']),
      objetivo: _txtN(r['goal_text']),
      resumen: _txtN(r['summary']),
      areaConocimientoId: _txt(r['knowledge_area_id']),
      nombreConocimiento: _txtN(
        _alguna(r, <String>['knowledge_area_name', 'area_name']),
      ),
      colorAcento: _txtN(r['accent_color']),
      iconoKey: _txtN(_alguna(r, <String>['icon_key', 'icon_hint'])),
      nivelDeclarado: NivelDeclarado.desdeApi(r['declared_level']),
      modoFuente: ModoFuente.desdeApi(r['source_mode']),
      origen: OrigenRuta.desdeApi(r['origin']),
      estado: EstadoRuta.desdeApi(r['status']),
      politicaCobertura: PoliticaCobertura.desdeApi(r['coverage_policy']),
      modulos: _ent(_alguna(r, <String>['module_count', 'modules_total'])),
      minutosEstimados: _entN(r['estimated_minutes']),
      estadoProgreso: EstadoProgreso.desdeApi(
        _alguna(p, <String>['progress_status', 'user_status']) ??
            (json['progress'] is Map ? p['status'] : null),
      ),
      modulosCompletados: _ent(p['modules_completed']),
      leccionesTotales: _ent(p['lessons_total']),
      leccionesCompletadas: _ent(p['lessons_completed']),
      porcentajeAvance: _dec(
        _alguna(p, <String>['completion_pct', 'progress_pct']),
      ),
      dominio: _dec(_alguna(p, <String>['mastery', 'mastery_pct'])),
      moduloActualId: _txtN(p['current_module_id']),
      leccionActualId: _txtN(p['current_lesson_id']),
      esPublica: _bol(r['is_public']),
      creadaEn: fechaHora(r['created_at']),
      confirmadaEn: fechaHora(r['confirmed_at']),
      completadaEn: fechaHora(_alguna(r, <String>['completed_at']) ?? p['completed_at']),
      archivadaEn: fechaHora(r['archived_at']),
      ultimaActividadEn: fechaHora(p['last_activity_at']),
    );
  }

  /// Identificador de la Ruta.
  final String id;

  /// Título ("Maestro de SQL").
  final String titulo;

  /// Objetivo escrito por el usuario.
  final String? objetivo;

  /// Resumen generado.
  final String? resumen;

  /// Conocimiento principal.
  final String areaConocimientoId;

  /// Nombre del conocimiento.
  final String? nombreConocimiento;

  /// Color de acento del territorio.
  final String? colorAcento;

  /// Clave del emblema.
  final String? iconoKey;

  /// Nivel declarado al crearla.
  final NivelDeclarado nivelDeclarado;

  /// Respaldo documental: con fuente, sin fuente o mixta.
  final ModoFuente modoFuente;

  /// Propia o Ruta del Reino.
  final OrigenRuta origen;

  /// Ciclo de vida del contenido.
  final EstadoRuta estado;

  /// Qué hacer con los temas sin respaldo.
  final PoliticaCobertura politicaCobertura;

  /// Número de módulos.
  final int modulos;

  /// Duración estimada total, en minutos.
  final int? minutosEstimados;

  /// Estado del avance del usuario.
  final EstadoProgreso estadoProgreso;

  /// Módulos completados.
  final int modulosCompletados;

  /// Lecciones de la Ruta.
  final int leccionesTotales;

  /// Lecciones completadas.
  final int leccionesCompletadas;

  /// Avance 0–100 calculado por el servidor.
  final double porcentajeAvance;

  /// Dominio del conocimiento asociado, 0–100.
  final double dominio;

  /// Dónde está el usuario ("Continuar").
  final String? moduloActualId;

  /// Siguiente lección recomendada.
  final String? leccionActualId;

  /// Visible para todos (solo Rutas del Reino).
  final bool esPublica;

  /// Alta de la Ruta.
  final DateTime? creadaEn;

  /// Confirmación del esquema por el usuario.
  final DateTime? confirmadaEn;

  /// Ruta completada.
  final DateTime? completadaEn;

  /// Archivada por el usuario.
  final DateTime? archivadaEn;

  /// Última actividad.
  final DateTime? ultimaActividadEn;

  /// ¿Es una Ruta del Reino (catálogo compartido)?
  bool get esDelReino => origen == OrigenRuta.reino;

  /// ¿Todavía se está generando contenido?
  bool get estaGenerando =>
      estado == EstadoRuta.generando || estado == EstadoRuta.borrador;
}

/// Lección tal como aparece en el mapa de la Ruta (P07).
class ResumenLeccion {
  const ResumenLeccion({
    required this.id,
    this.posicion = 1,
    this.titulo = '',
    this.segundosEstimados = 540,
    this.estadoContenido = EstadoContenido.pendiente,
    this.estado = EstadoProgreso.sinEmpezar,
    this.vecesCompletada = 0,
    this.contenidoEscaso = false,
    this.ultimoPaso = 0,
    this.precision,
    this.completadaEn,
  });

  /// Lee un nodo de lección del mapa de la Ruta.
  factory ResumenLeccion.desdeJson(Map<String, dynamic> json) => ResumenLeccion(
        id: _txt(_alguna(json, <String>['id', 'lesson_id'])),
        posicion: _ent(json['position'], 1),
        titulo: _txt(json['title']),
        segundosEstimados: _ent(json['estimated_seconds'], 540),
        estadoContenido: EstadoContenido.desdeApi(json['content_status']),
        estado: EstadoProgreso.desdeApi(json['status']),
        vecesCompletada: _ent(json['completion_count']),
        contenidoEscaso: _bol(json['is_low_content']),
        ultimoPaso: _ent(json['last_block_position']),
        precision: _decN(json['accuracy_pct']),
        completadaEn: fechaHora(
          _alguna(json, <String>['last_completed_at', 'first_completed_at']),
        ),
      );

  /// Identificador de la lección.
  final String id;

  /// Orden dentro del tema.
  final int posicion;

  /// Título.
  final String titulo;

  /// Duración estimada, en segundos.
  final int segundosEstimados;

  /// Estado de la generación del contenido.
  final EstadoContenido estadoContenido;

  /// Estado del avance del usuario.
  final EstadoProgreso estado;

  /// Cuántas veces la completó (regla anti-repetición).
  final int vecesCompletada;

  /// Material insuficiente: paga la mitad de XP y oro.
  final bool contenidoEscaso;

  /// Paso donde quedó, para reanudar.
  final int ultimoPaso;

  /// Precisión de la última pasada, 0–100.
  final double? precision;

  /// Última finalización.
  final DateTime? completadaEn;

  /// ¿Ya la completó al menos una vez?
  bool get estaCompletada =>
      estado == EstadoProgreso.completado || vecesCompletada > 0;

  /// ¿El contenido ya está escrito?
  bool get estaLista => estadoContenido == EstadoContenido.listo;

  /// Al repetirla no paga XP de lección, solo de preguntas nuevas.
  bool get esRepaso => vecesCompletada > 0;
}

/// Tema dentro de un módulo: granularidad del dominio fino y del repaso.
class Tema {
  const Tema({
    required this.id,
    this.moduloId,
    this.posicion = 1,
    this.titulo = '',
    this.objetivos = const <String>[],
    this.cobertura = NivelCobertura.completa,
    this.dificultad = Dificultad.media,
    this.minutosEstimados,
    this.estadoContenido = EstadoContenido.pendiente,
    this.dominio = 0,
    this.estado = EstadoDominio.sinEvidencia,
    this.esDebil = false,
    this.lecciones = const <ResumenLeccion>[],
    this.leccionesTotales = 0,
    this.leccionesCompletadas = 0,
  });

  /// Lee un tema del mapa de la Ruta o de la lista de temas débiles.
  factory Tema.desdeJson(Map<String, dynamic> json) {
    final List<ResumenLeccion> lecciones =
        _lista(json['lessons'], ResumenLeccion.desdeJson);
    return Tema(
      id: _txt(_alguna(json, <String>['id', 'topic_id'])),
      moduloId: _txtN(json['module_id']),
      posicion: _ent(json['position'], 1),
      titulo: _txt(_alguna(json, <String>['title', 'topic_title'])),
      objetivos: _textos(json['learning_objectives']),
      cobertura: NivelCobertura.desdeApi(json['coverage']),
      dificultad: Dificultad.desdeApi(json['difficulty']),
      minutosEstimados: _entN(json['estimated_minutes']),
      estadoContenido: EstadoContenido.desdeApi(json['content_status']),
      dominio: _dec(_alguna(json, <String>['mastery', 'mastery_pct'])),
      estado: EstadoDominio.desdeApi(json['status']),
      esDebil: _bol(json['is_weak']),
      lecciones: lecciones,
      leccionesTotales: _ent(
        _alguna(json, <String>['lessons_total', 'lesson_count']),
        lecciones.length,
      ),
      leccionesCompletadas: _ent(
        json['lessons_completed'],
        lecciones.where((ResumenLeccion l) => l.estaCompletada).length,
      ),
    );
  }

  /// Identificador del tema.
  final String id;

  /// Módulo al que pertenece.
  final String? moduloId;

  /// Orden dentro del módulo.
  final int posicion;

  /// Título ("INNER vs LEFT JOIN").
  final String titulo;

  /// Objetivos de aprendizaje declarados.
  final List<String> objetivos;

  /// Cobertura del material para el tema.
  final NivelCobertura cobertura;

  /// Dificultad declarada.
  final Dificultad dificultad;

  /// Duración estimada, en minutos.
  final int? minutosEstimados;

  /// Estado de la generación del contenido.
  final EstadoContenido estadoContenido;

  /// Dominio del tema, 0–100.
  final double dominio;

  /// Estado de dominio.
  final EstadoDominio estado;

  /// `true` cuando el servidor lo marca como debilidad.
  final bool esDebil;

  /// Lecciones del tema.
  final List<ResumenLeccion> lecciones;

  /// Lecciones totales.
  final int leccionesTotales;

  /// Lecciones completadas.
  final int leccionesCompletadas;

  /// ¿El material no cubre bien el tema?
  bool get esConocimientoGeneral => cobertura == NivelCobertura.insuficiente;
}

/// Entrada del Desafío del módulo, tal como aparece en el mapa.
class ResumenEvaluacion {
  const ResumenEvaluacion({
    required this.id,
    this.moduloId,
    this.titulo = 'Prueba del módulo',
    this.preguntas = 10,
    this.puntajeAprobacion = 70,
    this.estadoContenido = EstadoContenido.pendiente,
    this.intentosUsados = 0,
    this.intentosMaximosPorDia = 2,
    this.mejorPuntaje,
    this.aprobada = false,
    this.puedeEmpezar = false,
    this.enfriamientoHasta,
  });

  /// Lee el objeto `assessment` del mapa de la Ruta o de `AssessmentInfoOut`.
  factory ResumenEvaluacion.desdeJson(Map<String, dynamic> json) =>
      ResumenEvaluacion(
        id: _txt(_alguna(json, <String>['id', 'assessment_id'])),
        moduloId: _txtN(json['module_id']),
        titulo: _txt(json['title'], 'Prueba del módulo'),
        preguntas: _ent(json['question_count'], 10),
        puntajeAprobacion: _dec(json['pass_score'], 70),
        estadoContenido: EstadoContenido.desdeApi(json['content_status']),
        intentosUsados: _ent(
          _alguna(json, <String>['attempts_used', 'assessment_attempts']),
        ),
        intentosMaximosPorDia: _ent(json['max_attempts_per_day'], 2),
        mejorPuntaje: _decN(
          _alguna(json, <String>['best_score', 'assessment_best_score']),
        ),
        aprobada: _bol(_alguna(json, <String>['passed', 'is_passed'])),
        puedeEmpezar: _bol(json['can_start']),
        enfriamientoHasta: fechaHora(json['cooldown_until']),
      );

  /// Identificador de la evaluación.
  final String id;

  /// Módulo evaluado.
  final String? moduloId;

  /// Nombre narrativo.
  final String titulo;

  /// Preguntas por intento.
  final int preguntas;

  /// Umbral de aprobación en porcentaje.
  final double puntajeAprobacion;

  /// Estado del banco de preguntas.
  final EstadoContenido estadoContenido;

  /// Intentos ya realizados.
  final int intentosUsados;

  /// Tope diario de intentos.
  final int intentosMaximosPorDia;

  /// Mejor puntaje bruto obtenido.
  final double? mejorPuntaje;

  /// ¿Ya la aprobó?
  final bool aprobada;

  /// ¿El servidor autoriza empezar ahora?
  final bool puedeEmpezar;

  /// Fin del enfriamiento tras reprobar.
  final DateTime? enfriamientoHasta;

  /// ¿Está en enfriamiento en este instante?
  bool get enEnfriamiento {
    final DateTime? hasta = enfriamientoHasta;
    return hasta != null && hasta.isAfter(DateTime.now());
  }
}

/// Módulo de una Ruta: zona del territorio con sus temas y su Desafío.
class ModuloRuta {
  const ModuloRuta({
    required this.id,
    this.rutaId,
    this.posicion = 1,
    this.titulo = '',
    this.nombreNarrativo,
    this.resumen,
    this.dificultad = Dificultad.media,
    this.minutosEstimados,
    this.estadoContenido = EstadoContenido.pendiente,
    this.estado = EstadoModulo.bloqueado,
    this.dominio = 0,
    this.temas = const <Tema>[],
    this.leccionesTotales = 0,
    this.leccionesCompletadas = 0,
    this.evaluacion,
    this.estrellas = 0,
    this.motivoBloqueo,
    this.desbloqueadoEn,
    this.completadoEn,
  });

  /// Lee un módulo del mapa de la Ruta (`PathModuleOut`).
  factory ModuloRuta.desdeJson(Map<String, dynamic> json) {
    final List<Tema> temas = _lista(json['topics'], Tema.desdeJson);
    return ModuloRuta(
      id: _txt(_alguna(json, <String>['id', 'module_id'])),
      rutaId: _txtN(_alguna(json, <String>['learning_path_id', 'path_id'])),
      posicion: _ent(json['position'], 1),
      titulo: _txt(json['title']),
      nombreNarrativo: _txtN(json['flavor_name']),
      resumen: _txtN(json['summary']),
      dificultad: Dificultad.desdeApi(json['difficulty']),
      minutosEstimados: _entN(json['estimated_minutes']),
      estadoContenido: EstadoContenido.desdeApi(json['content_status']),
      estado: EstadoModulo.desdeApi(json['status']),
      dominio: _dec(_alguna(json, <String>['mastery', 'mastery_pct'])),
      temas: temas,
      leccionesTotales: _ent(
        _alguna(json, <String>['lessons_total', 'lesson_count']),
      ),
      leccionesCompletadas: _ent(json['lessons_completed']),
      evaluacion: json['assessment'] is Map
          ? ResumenEvaluacion.desdeJson(_mapa(json['assessment']))
          : null,
      estrellas: _ent(json['stars']),
      motivoBloqueo: _txtN(_alguna(json, <String>['locked_reason', 'lock_reason'])),
      desbloqueadoEn: fechaHora(json['unlocked_at']),
      completadoEn: fechaHora(json['completed_at']),
    );
  }

  /// Identificador del módulo.
  final String id;

  /// Ruta a la que pertenece.
  final String? rutaId;

  /// Orden 1..n dentro de la Ruta.
  final int posicion;

  /// Título temático ("JOINs").
  final String titulo;

  /// Nombre narrativo de la zona.
  final String? nombreNarrativo;

  /// Resumen del módulo.
  final String? resumen;

  /// Dificultad declarada.
  final Dificultad dificultad;

  /// Duración estimada, en minutos.
  final int? minutosEstimados;

  /// Estado de la generación perezosa.
  final EstadoContenido estadoContenido;

  /// Estado del módulo para el usuario.
  final EstadoModulo estado;

  /// Dominio del módulo, 0–100.
  final double dominio;

  /// Temas del módulo.
  final List<Tema> temas;

  /// Lecciones del módulo.
  final int leccionesTotales;

  /// Lecciones completadas.
  final int leccionesCompletadas;

  /// Desafío del módulo.
  final ResumenEvaluacion? evaluacion;

  /// Estrellas de la evaluación, 0–3.
  final int estrellas;

  /// Frase de por qué está bloqueado ("Completa Filtros para desbloquear").
  final String? motivoBloqueo;

  /// Momento del desbloqueo.
  final DateTime? desbloqueadoEn;

  /// Momento en que se completó.
  final DateTime? completadoEn;

  /// Nombre a mostrar: el narrativo si existe, si no el temático.
  String get nombreVisible => nombreNarrativo ?? titulo;

  /// ¿Está bloqueado por el avance?
  bool get estaBloqueado => estado == EstadoModulo.bloqueado;

  /// ¿Su contenido sigue escribiéndose?
  bool get enConstruccion =>
      estadoContenido == EstadoContenido.pendiente ||
      estadoContenido == EstadoContenido.generando;

  /// Todas las lecciones del módulo, en orden.
  List<ResumenLeccion> get todasLasLecciones => <ResumenLeccion>[
        for (final Tema t in temas) ...t.lecciones,
      ];
}

/// Mapa completo de la Ruta (`PathDetailOut`, P07).
class DetalleRuta {
  const DetalleRuta({
    required this.ruta,
    this.modulos = const <ModuloRuta>[],
    this.avisosCobertura = const <AvisoCobertura>[],
    this.documentos = const <Documento>[],
    this.itemDeConocimiento,
    this.puedeConfirmar = false,
  });

  /// Lee `PathDetailOut`.
  factory DetalleRuta.desdeJson(Map<String, dynamic> json) => DetalleRuta(
        ruta: ResumenRuta.desdeJson(json),
        modulos: _lista(json['modules'], ModuloRuta.desdeJson),
        avisosCobertura: _lista(json['coverage_notes'], AvisoCobertura.desdeJson),
        documentos: _lista(
          _alguna(json, <String>['sources', 'documents']),
          Documento.desdeJson,
        ),
        itemDeConocimiento: json['knowledge_item'] is Map
            ? Item.desdeJson(_mapa(json['knowledge_item']))
            : null,
        puedeConfirmar: _esperaConfirmacion(json),
      );

  /// ¿El esquema está esperando que el aprendiz lo revise y lo confirme?
  ///
  /// `PathDetailOut` **no** trae `can_confirm`: lo dice el estado de la Ruta.
  /// Leer un campo que el servidor nunca envía dejaba el botón de confirmar
  /// apagado para siempre, y confirmar es lo único que dispara la escritura de
  /// las lecciones: una Ruta propia se quedaba en el esquema, sin contenido y
  /// sin forma de avanzar.
  ///
  /// Las Rutas del Reino vienen escritas y no se confirman.
  static bool _esperaConfirmacion(Map<String, dynamic> json) {
    final Object? explicito = _alguna(json, <String>['can_confirm', 'needs_confirm']);
    if (explicito != null) return _bol(explicito);
    final Map<String, dynamic> ruta = _mapa(_alguna(json, <String>['path']) ?? json);
    if (_bol(_alguna(ruta, <String>['is_seed']))) return false;
    return EstadoRuta.desdeApi(ruta['status']) == EstadoRuta.porRevisar;
  }

  /// Cabecera de la Ruta con su avance.
  final ResumenRuta ruta;

  /// Módulos en orden, con temas y lecciones.
  final List<ModuloRuta> modulos;

  /// Avisos de cobertura de la Fase A.
  final List<AvisoCobertura> avisosCobertura;

  /// Documentos que respaldan la Ruta.
  final List<Documento> documentos;

  /// Ítem que se gana al completar la Ruta ("Espada del SQL").
  final Item? itemDeConocimiento;

  /// `true` mientras el esquema espera la confirmación del usuario.
  final bool puedeConfirmar;

  /// Atajo al identificador de la Ruta.
  String get id => ruta.id;

  /// Siguiente módulo sobre el que actuar, si lo hay.
  ModuloRuta? get moduloActual {
    for (final ModuloRuta m in modulos) {
      if (m.estado == EstadoModulo.enProgreso) return m;
    }
    for (final ModuloRuta m in modulos) {
      if (m.estado == EstadoModulo.disponible) return m;
    }
    return modulos.isEmpty ? null : modulos.first;
  }
}

/// Trabajo de generación o de ingesta (`JobOut`), base del polling de P06.
class Trabajo {
  const Trabajo({
    required this.id,
    this.tipo = TipoTrabajo.disenoRuta,
    this.estado = EstadoTrabajo.pendiente,
    this.porcentaje = 0,
    this.etiqueta,
    this.error,
    this.rutaId,
    this.encoladoEn,
    this.iniciadoEn,
    this.terminadoEn,
  });

  /// Lee `{id, job_type, status, progress_pct, progress_label, error}`.
  factory Trabajo.desdeJson(Map<String, dynamic> json) => Trabajo(
        id: _txt(_alguna(json, <String>['id', 'job_id'])),
        tipo: TipoTrabajo.desdeApi(json['job_type']),
        estado: EstadoTrabajo.desdeApi(json['status']),
        porcentaje: _dec(json['progress_pct']),
        etiqueta: _txtN(json['progress_label']),
        error: _txtN(_alguna(json, <String>['error', 'error_message'])),
        rutaId: _txtN(json['learning_path_id']),
        encoladoEn: fechaHora(json['queued_at']),
        iniciadoEn: fechaHora(json['started_at']),
        terminadoEn: fechaHora(json['finished_at']),
      );

  /// Identificador del trabajo.
  final String id;

  /// Qué está haciendo.
  final TipoTrabajo tipo;

  /// Estado del trabajo.
  final EstadoTrabajo estado;

  /// Progreso 0–100.
  final double porcentaje;

  /// Etapa visible ("Diseñando módulos").
  final String? etiqueta;

  /// Último error, si falló.
  final String? error;

  /// Ruta afectada.
  final String? rutaId;

  /// Momento en que se encoló.
  final DateTime? encoladoEn;

  /// Momento en que empezó.
  final DateTime? iniciadoEn;

  /// Momento en que terminó.
  final DateTime? terminadoEn;

  /// ¿Sigue en marcha?
  bool get enMarcha =>
      estado == EstadoTrabajo.pendiente || estado == EstadoTrabajo.ejecutando;

  /// ¿Terminó bien?
  bool get termino => estado == EstadoTrabajo.logrado;

  /// ¿Falló de forma definitiva?
  bool get fallo =>
      estado == EstadoTrabajo.fallido || estado == EstadoTrabajo.cancelado;
}

/// Una etapa con nombre de la pantalla de generación (P06).
class EtapaGeneracion {
  const EtapaGeneracion({
    this.clave = '',
    this.titulo = '',
    this.estado = EstadoTrabajo.pendiente,
    this.porcentaje = 0,
    this.detalle,
  });

  /// Lee un elemento de `stages[]`.
  factory EtapaGeneracion.desdeJson(Map<String, dynamic> json) => EtapaGeneracion(
        clave: _txt(_alguna(json, <String>['key', 'stage', 'code'])),
        titulo: _txt(_alguna(json, <String>['title', 'label', 'name'])),
        estado: EstadoTrabajo.desdeApi(json['status']),
        porcentaje: _dec(json['progress_pct']),
        detalle: _txtN(_alguna(json, <String>['detail', 'message', 'fact'])),
      );

  /// Clave estable de la etapa.
  final String clave;

  /// Nombre visible ("Leyendo documentos").
  final String titulo;

  /// Estado de la etapa.
  final EstadoTrabajo estado;

  /// Progreso de la etapa, 0–100.
  final double porcentaje;

  /// Dato real para hacer la espera tolerable.
  final String? detalle;

  /// ¿Ya está hecha?
  bool get estaHecha => estado == EstadoTrabajo.logrado;

  /// ¿Es la etapa en curso?
  bool get enCurso => estado == EstadoTrabajo.ejecutando;
}

/// Estado agregado de la generación de una Ruta (`GenerationStatusOut`, P06).
class EstadoGeneracion {
  const EstadoGeneracion({
    this.estado = EstadoTrabajo.pendiente,
    this.etapa,
    this.porcentaje = 0,
    this.primerModuloListo = false,
    this.segundosEstimados,
    this.trabajos = const <Trabajo>[],
    this.etapas = const <EtapaGeneracion>[],
    this.error,
    this.rutaId,
  });

  /// Lee `{status, stage, progress_pct, first_module_ready, eta_seconds, jobs[]}`.
  factory EstadoGeneracion.desdeJson(Map<String, dynamic> json) => EstadoGeneracion(
        estado: EstadoTrabajo.desdeApi(json['status']),
        etapa: _txtN(_alguna(json, <String>['stage', 'stage_label'])),
        porcentaje: _dec(json['progress_pct']),
        primerModuloListo: _bol(json['first_module_ready']),
        segundosEstimados: _entN(json['eta_seconds']),
        trabajos: _lista(json['jobs'], Trabajo.desdeJson),
        etapas: _lista(json['stages'], EtapaGeneracion.desdeJson),
        error: _txtN(_alguna(json, <String>['error', 'error_message'])),
        rutaId: _txtN(_alguna(json, <String>['path_id', 'learning_path_id'])),
      );

  /// Estado global de la generación.
  final EstadoTrabajo estado;

  /// Nombre de la etapa en curso.
  final String? etapa;

  /// Progreso global 0–100.
  final double porcentaje;

  /// `true` cuando ya se puede empezar el módulo 1.
  final bool primerModuloListo;

  /// Estimación honesta que falta, en segundos.
  final int? segundosEstimados;

  /// Trabajos que componen la generación.
  final List<Trabajo> trabajos;

  /// Etapas con nombre para la lista de P06.
  final List<EtapaGeneracion> etapas;

  /// Mensaje de fallo, si lo hubo.
  final String? error;

  /// Ruta que se está construyendo.
  final String? rutaId;

  /// ¿Sigue trabajando el Reino?
  bool get enMarcha =>
      estado == EstadoTrabajo.pendiente || estado == EstadoTrabajo.ejecutando;

  /// ¿Terminó del todo?
  bool get termino => estado == EstadoTrabajo.logrado;

  /// ¿Falló?
  bool get fallo =>
      estado == EstadoTrabajo.fallido || estado == EstadoTrabajo.cancelado;
}

/// Respuesta de `POST /paths`: la Ruta recién creada y su trabajo (`PathCreatedOut`).
class RutaCreada {
  const RutaCreada({required this.ruta, this.trabajo});

  /// Lee `{path, job}`.
  factory RutaCreada.desdeJson(Map<String, dynamic> json) => RutaCreada(
        ruta: ResumenRuta.desdeJson(
          json['path'] is Map ? _mapa(json['path']) : json,
        ),
        trabajo: json['job'] is Map ? Trabajo.desdeJson(_mapa(json['job'])) : null,
      );

  /// Ruta creada, todavía en borrador.
  final ResumenRuta ruta;

  /// Trabajo de la Fase A ya encolado.
  final Trabajo? trabajo;
}

/// Material subido por el usuario (`DocumentOut`).
class Documento {
  const Documento({
    required this.id,
    this.titulo = '',
    this.tipo = TipoDocumento.pdf,
    this.nombreArchivo,
    this.estado = EstadoDocumento.subido,
    this.bytes = 0,
    this.paginas,
    this.palabras,
    this.fragmentos = 0,
    this.error,
    this.creadoEn,
    this.procesadoEn,
    this.trabajo,
  });

  /// Lee `DocumentOut`; `job` solo llega al subir o al pegar texto.
  factory Documento.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> d =
        json['document'] is Map ? _mapa(json['document']) : json;
    return Documento(
      id: _txt(_alguna(d, <String>['id', 'document_id'])),
      titulo: _txt(d['title']),
      tipo: TipoDocumento.desdeApi(d['document_type']),
      nombreArchivo: _txtN(d['original_filename']),
      estado: EstadoDocumento.desdeApi(d['status']),
      bytes: _ent(d['byte_size']),
      paginas: _entN(d['page_count']),
      palabras: _entN(d['word_count']),
      fragmentos: _ent(d['chunk_count']),
      error: _txtN(_alguna(d, <String>['error_message', 'error'])),
      creadoEn: fechaHora(d['created_at']),
      procesadoEn: fechaHora(d['processed_at']),
      trabajo: json['job'] is Map ? Trabajo.desdeJson(_mapa(json['job'])) : null,
    );
  }

  /// Identificador del documento.
  final String id;

  /// Título visible.
  final String titulo;

  /// Formato de origen.
  final TipoDocumento tipo;

  /// Nombre del archivo subido.
  final String? nombreArchivo;

  /// Estado del procesamiento.
  final EstadoDocumento estado;

  /// Tamaño en bytes.
  final int bytes;

  /// Páginas detectadas.
  final int? paginas;

  /// Palabras detectadas.
  final int? palabras;

  /// Fragmentos indexados.
  final int fragmentos;

  /// Motivo de rechazo o de fallo.
  final String? error;

  /// Momento de la subida.
  final DateTime? creadoEn;

  /// Fin de la ingesta.
  final DateTime? procesadoEn;

  /// Trabajo de ingesta encolado.
  final Trabajo? trabajo;

  /// ¿Está listo para respaldar contenido?
  bool get estaListo => estado.estaListo;

  /// ¿Sigue procesándose?
  bool get enProceso => estado.estaEnCurso;

  /// Tamaño legible ("2,1 MB").
  String get tamanoLegible {
    if (bytes <= 0) return '';
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) {
      return '${(bytes / 1024).toStringAsFixed(0)} KB';
    }
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}

/// Fragmento original del material para la hoja "Fuente" (`ChunkOut`).
class Fragmento {
  const Fragmento({
    required this.id,
    this.documentoId = '',
    this.tituloDocumento,
    this.tipo = TipoFragmento.prosa,
    this.encabezados = const <String>[],
    this.texto = '',
    this.paginaInicio,
    this.paginaFin,
    this.indice = 0,
  });

  /// Lee `ChunkOut`.
  factory Fragmento.desdeJson(Map<String, dynamic> json) => Fragmento(
        id: _txt(_alguna(json, <String>['id', 'chunk_id'])),
        documentoId: _txt(json['document_id']),
        tituloDocumento: _txtN(
          _alguna(json, <String>['document_title', 'title']),
        ),
        tipo: TipoFragmento.desdeApi(json['chunk_type']),
        encabezados: _textos(json['heading_path']),
        texto: _txt(json['text']),
        paginaInicio: _entN(json['page_start']),
        paginaFin: _entN(json['page_end']),
        indice: _ent(json['chunk_index']),
      );

  /// Identificador del fragmento.
  final String id;

  /// Documento de origen.
  final String documentoId;

  /// Título del documento, para la cabecera de la hoja.
  final String? tituloDocumento;

  /// Prosa, código, tabla o lista.
  final TipoFragmento tipo;

  /// Ruta de encabezados ("Capítulo 5. JOINs" › "LEFT JOIN").
  final List<String> encabezados;

  /// Texto normalizado del fragmento.
  final String texto;

  /// Página inicial.
  final int? paginaInicio;

  /// Página final.
  final int? paginaFin;

  /// Orden dentro de la versión del documento.
  final int indice;

  /// Referencia legible de página ("pp. 34–35").
  String get referenciaPaginas {
    final int? a = paginaInicio;
    final int? b = paginaFin;
    if (a == null) return '';
    if (b == null || b == a) return 'p. $a';
    return 'pp. $a–$b';
  }
}

// ---------------------------------------------------------------------------
// §7.6 Lección, respuestas y recompensas
// ---------------------------------------------------------------------------

/// Cita de procedencia: de qué material salió un bloque o una pregunta.
class Procedencia {
  const Procedencia({
    this.tipoContenido = TipoContenido.bloque,
    this.contenidoId = '',
    this.clave,
    this.origen = OrigenContenido.material,
    this.fragmentoId,
    this.documentoId,
    this.tituloDocumento,
    this.paginaInicio,
    this.paginaFin,
    this.extracto,
    this.posicionRecuperacion,
    this.procesadoEn,
  });

  /// Lee `ProvenanceOut`.
  factory Procedencia.desdeJson(Map<String, dynamic> json) => Procedencia(
        tipoContenido: TipoContenido.desdeApi(json['content_type']),
        contenidoId: _txt(json['content_id']),
        clave: _txtN(json['block_key']),
        origen: OrigenContenido.desdeApi(json['origin']),
        fragmentoId: _txtN(json['chunk_id']),
        documentoId: _txtN(json['document_id']),
        tituloDocumento:
            _txtN(_alguna(json, <String>['document_title', 'title', 'source_title'])),
        paginaInicio: _entN(_alguna(json, <String>['page_start', 'page'])),
        paginaFin: _entN(json['page_end']),
        extracto: _txtN(_alguna(json, <String>['excerpt', 'snippet', 'text'])),
        posicionRecuperacion: _entN(json['retrieval_rank']),
        procesadoEn: fechaHora(json['processed_at']),
      );

  /// Qué pieza generada se está trazando.
  final TipoContenido tipoContenido;

  /// Identificador de la pieza generada.
  final String contenidoId;

  /// Sub-elemento (posición del bloque o id de la pregunta).
  final String? clave;

  /// Material propio o saber del Reino.
  final OrigenContenido origen;

  /// Fragmento que respalda el contenido, para abrir la hoja "Fuente".
  final String? fragmentoId;

  /// Documento del que proviene.
  final String? documentoId;

  /// Título del documento, para el chip de fuente.
  final String? tituloDocumento;

  /// Página inicial dentro del documento.
  final int? paginaInicio;

  /// Página final dentro del documento.
  final int? paginaFin;

  /// Extracto literal del material, si el servidor lo envía.
  final String? extracto;

  /// Posición en la recuperación híbrida (auditoría).
  final int? posicionRecuperacion;

  /// Cuándo se procesó el material.
  final DateTime? procesadoEn;

  /// ¿La cita apunta a material del usuario?
  bool get esDelMaterial => origen == OrigenContenido.material;

  /// Referencia legible de páginas ("pp. 34–35").
  String get referenciaPaginas {
    final int? a = paginaInicio;
    final int? b = paginaFin;
    if (a == null) return '';
    if (b == null || b == a) return 'p. $a';
    return 'pp. $a–$b';
  }

  /// Etiqueta del chip de fuente ("Guía de SQL · pp. 34–35").
  String get etiqueta {
    if (!esDelMaterial) return OrigenContenido.saberDelReino.etiqueta;
    final String titulo = tituloDocumento ?? 'Tu material';
    final String paginas = referenciaPaginas;
    return paginas.isEmpty ? titulo : '$titulo · $paginas';
  }
}

/// Cobertura declarada de un objetivo de la lección (`coverage_report`).
class ObjetivoCobertura {
  const ObjetivoCobertura({
    this.objetivo = '',
    this.nivel = NivelCobertura.completa,
  });

  /// Lee `{objective, status}`.
  factory ObjetivoCobertura.desdeJson(Map<String, dynamic> json) =>
      ObjetivoCobertura(
        objetivo: _txt(_alguna(json, <String>['objective', 'objetivo'])),
        nivel: NivelCobertura.desdeApi(_alguna(json, <String>['status', 'coverage'])),
      );

  /// Objetivo de aprendizaje enunciado.
  final String objetivo;

  /// Cuánto lo respalda el material.
  final NivelCobertura nivel;
}

/// Opción, pareja o elemento ordenable de una pregunta.
/// Cierra una sentencia SQL con punto y coma solo si le falta.
String _conPuntoYComa(String sentencia) =>
    sentencia.endsWith(';') ? sentencia : '$sentencia;';

/// Marca de hueco de una plantilla de "completa": `{{0}}`, `{{1}}`…
final RegExp _marcaDeHueco = RegExp(r'\{\{\s*\d+\s*\}\}');

class OpcionPregunta {
  const OpcionPregunta({
    this.clave = '',
    this.texto = '',
    this.indice = 0,
    this.pareja,
    this.imagenKey,
  });

  /// Lee `{key, text}`; tolera `{id, label}` y otras variantes.
  factory OpcionPregunta.desdeJson(Map<String, dynamic> json, [int indice = 0]) =>
      OpcionPregunta(
        clave: _txt(
          _alguna(json, <String>['key', 'id', 'value', 'left']),
          indice.toString(),
        ),
        texto: _txt(
          _alguna(json, <String>['text', 'label', 'content', 'left_text', 'left']),
        ),
        indice: _ent(json['position'], indice),
        pareja: _txtN(_alguna(json, <String>['right', 'right_text', 'match'])),
        imagenKey: _txtN(_alguna(json, <String>['image_key', 'icon_key'])),
      );

  /// Construye la opción a partir de un valor suelto de la lista.
  static OpcionPregunta desdeBruto(Object? bruto, int indice) {
    if (bruto is Map) {
      return OpcionPregunta.desdeJson(Map<String, dynamic>.from(bruto), indice);
    }
    return OpcionPregunta(
      clave: indice.toString(),
      texto: _txt(bruto),
      indice: indice,
    );
  }

  /// Clave estable con la que se envía la respuesta.
  final String clave;

  /// Texto que se muestra.
  final String texto;

  /// Posición original en la lista.
  final int indice;

  /// Lado derecho, cuando la pregunta es de relacionar.
  final String? pareja;

  /// Ilustración opcional.
  final String? imagenKey;
}

/// Pregunta o ejercicio presentado al usuario. **Jamás trae `answer_key`.**
class Pregunta {
  const Pregunta({
    required this.id,
    this.tipo = TipoPregunta.opcionMultiple,
    this.dificultad = Dificultad.media,
    this.enunciado = '',
    this.cuerpo = const <String, dynamic>{},
    this.explicacion,
    this.objetivo,
    this.segundosEstimados = 45,
    this.temaId,
    this.tituloTema,
    this.leccionId,
    this.origen = OrigenContenido.material,
    this.posicion = 0,
    this.procedencia = const <Procedencia>[],
  });

  /// Lee `QuestionOut` sin clave de corrección.
  factory Pregunta.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> cuerpo = _mapa(
      _alguna(json, <String>['body', 'payload', 'content']),
    );
    return Pregunta(
      id: _txt(_alguna(json, <String>['id', 'question_id'])),
      tipo: TipoPregunta.desdeApi(_alguna(json, <String>['question_type', 'type'])),
      dificultad: Dificultad.desdeApi(json['difficulty']),
      enunciado: _txt(_alguna(json, <String>['stem', 'prompt', 'text'])),
      cuerpo: cuerpo,
      explicacion: _txtN(json['explanation']),
      objetivo: _txtN(json['learning_objective']),
      segundosEstimados: _ent(json['estimated_seconds'], 45),
      temaId: _txtN(json['topic_id']),
      tituloTema: _txtN(_alguna(json, <String>['topic_title', 'topic_name'])),
      leccionId: _txtN(json['lesson_id']),
      origen: OrigenContenido.desdeApi(json['origin']),
      posicion: _ent(_alguna(json, <String>['position', 'index'])),
      procedencia: _lista(
        _alguna(json, <String>['provenance', 'citations']),
        Procedencia.desdeJson,
      ),
    );
  }

  /// Identificador de la pregunta.
  final String id;

  /// Tipo, que decide el widget de respuesta.
  final TipoPregunta tipo;

  /// Dificultad declarada.
  final Dificultad dificultad;

  /// Enunciado.
  final String enunciado;

  /// Cuerpo por tipo, tal cual lo envía el servidor.
  final Map<String, dynamic> cuerpo;

  /// Explicación; solo llega en la revisión, nunca antes de responder.
  final String? explicacion;

  /// Objetivo de aprendizaje que evalúa.
  final String? objetivo;

  /// Duración estimada en segundos.
  final int segundosEstimados;

  /// Tema al que pertenece.
  final String? temaId;

  /// Título del tema, para la miga de pan.
  final String? tituloTema;

  /// Lección donde aparece intercalada, si aplica.
  final String? leccionId;

  /// Respaldo de la pregunta.
  final OrigenContenido origen;

  /// Posición dentro de la actividad.
  final int posicion;

  /// Citas de procedencia.
  final List<Procedencia> procedencia;

  /// Alternativas de opción múltiple, verdadero/falso u ordenar.
  List<OpcionPregunta> get opciones {
    final Object? crudo = cuerpo['options'] ?? cuerpo['choices'] ?? cuerpo['items'];
    if (crudo is! List) return const <OpcionPregunta>[];
    final List<OpcionPregunta> salida = <OpcionPregunta>[];
    for (int i = 0; i < crudo.length; i++) {
      salida.add(OpcionPregunta.desdeBruto(crudo[i], i));
    }
    return salida;
  }

  /// Columna izquierda del ejercicio de relacionar.
  ///
  /// El cuerpo que manda el Reino trae `left` y `right`; `pairs` vive en la
  /// clave de corrección y **nunca** viaja al cliente. Leer `pairs` aquí dejaba
  /// la pantalla en blanco y la pregunta sin forma de responderse.
  List<OpcionPregunta> get parejas {
    final Object? crudo = cuerpo['left'] ?? cuerpo['pairs'] ?? cuerpo['matches'];
    if (crudo is! List) return const <OpcionPregunta>[];
    final List<OpcionPregunta> salida = <OpcionPregunta>[];
    for (int i = 0; i < crudo.length; i++) {
      salida.add(OpcionPregunta.desdeBruto(crudo[i], i));
    }
    return salida;
  }

  /// Alternativas del lado derecho, ya barajadas por el servidor.
  ///
  /// Llevan su clave porque el corrector compara **claves**, no textos: mandar
  /// lo que se lee en pantalla daría siempre cero.
  List<OpcionPregunta> get candidatas {
    final Object? crudo =
        cuerpo['right'] ?? cuerpo['right_options'] ?? cuerpo['candidates'];
    if (crudo is List) {
      final List<OpcionPregunta> salida = <OpcionPregunta>[];
      for (int i = 0; i < crudo.length; i++) {
        salida.add(OpcionPregunta.desdeBruto(crudo[i], i));
      }
      return salida;
    }
    return const <OpcionPregunta>[];
  }

  /// Trozos de texto de "completa el hueco"; los huecos van como `null`.
  ///
  /// El Reino manda una `template` con marcas `{{0}}`, `{{1}}`… no una lista de
  /// segmentos. Sin traducirla, la frase no se pintaba nunca y el aprendiz veía
  /// un campo de texto suelto sin saber qué completaba.
  List<String?> get segmentos {
    final Object? crudo = cuerpo['segments'] ?? cuerpo['parts'];
    if (crudo is List) {
      return crudo.map((Object? e) => e?.toString()).toList(growable: false);
    }

    // La semilla manda la frase en `template`, con marcas desde `{{0}}`; el
    // generador la manda en `text`, con marcas desde `{{1}}`. Valen las dos:
    // lo que importa es el orden en que aparecen las marcas, que es el orden
    // en que el corrector espera los huecos.
    String plantilla = _txt(cuerpo['template']);
    if (plantilla.isEmpty) {
      final String alternativa = _txt(cuerpo['text']);
      if (_marcaDeHueco.hasMatch(alternativa)) plantilla = alternativa;
    }
    if (plantilla.isEmpty) return const <String?>[];

    final List<String?> salida = <String?>[];
    int desde = 0;
    for (final RegExpMatch m in _marcaDeHueco.allMatches(plantilla)) {
      final String antes = plantilla.substring(desde, m.start);
      if (antes.isNotEmpty) salida.add(antes);
      salida.add(null);
      desde = m.end;
    }
    final String cola = plantilla.substring(desde);
    if (cola.isNotEmpty) salida.add(cola);
    return salida;
  }

  /// Cuántos huecos hay que rellenar.
  int get huecos {
    final Object? declarados = cuerpo['blanks'];
    if (declarados is List && declarados.isNotEmpty) return declarados.length;
    final int declarado = _ent(cuerpo['blank_count'] ?? declarados);
    if (declarado > 0) return declarado;
    final int porSegmentos = segmentos.where((String? s) => s == null).length;
    return porSegmentos > 0 ? porSegmentos : 1;
  }

  /// Pista de cada hueco, cuando el Reino la manda (`blanks[i].hint`).
  List<String?> get pistasDeHuecos {
    final Object? crudo = cuerpo['blanks'];
    if (crudo is! List) return const <String?>[];
    return <String?>[
      for (final Object? e in crudo)
        if (e is Map) _txtN(e['hint']) else null,
    ];
  }

  /// Criterios de la rúbrica de una respuesta abierta.
  List<String> get rubrica => _textos(cuerpo['rubric'] ?? cuerpo['criteria']);

  /// Esquema SQL de apoyo del ejercicio.
  String? get esquemaSql => _txtN(cuerpo['schema_sql']);

  /// Datos de ejemplo del ejercicio SQL.
  ///
  /// Viajan como lista de sentencias. Volcarlas con `toString` pintaba el
  /// literal de Dart, con corchetes y comas, en mitad de la pantalla.
  String? get datosSemilla {
    final Object? crudo = cuerpo['seed_data'];
    if (crudo is List) {
      final List<String> lineas = <String>[
        for (final Object? e in crudo)
          if (e != null && e.toString().trim().isNotEmpty)
            // Muchas ya traen su punto y coma: anadirlo siempre lo duplica.
            _conPuntoYComa(e.toString().trim()),
      ];
      return lineas.isEmpty ? null : lineas.join('\n');
    }
    return _txtN(crudo);
  }

  /// Lenguaje del editor de código.
  String get lenguaje => _txt(cuerpo['language'], 'sql');

  /// Texto de arranque del editor.
  String? get plantillaRespuesta =>
      _txtN(cuerpo['starter_code'] ?? cuerpo['template']);

  /// Enunciado extendido del caso de estudio.
  String? get contexto => _txtN(cuerpo['context'] ?? cuerpo['scenario']);

  /// Máximo de caracteres admitido en una respuesta abierta.
  int get maximoCaracteres => _ent(cuerpo['max_chars'], 600);

  /// ¿Se responde escribiendo texto libre?
  bool get esAbierta =>
      tipo == TipoPregunta.respuestaCorta ||
      tipo == TipoPregunta.casoEstudio ||
      tipo == TipoPregunta.ejercicioSql ||
      tipo == TipoPregunta.ejercicioCodigo;
}

/// Bloque ordenado de la lección (`LessonBlockOut`).
class BloqueLeccion {
  const BloqueLeccion({
    required this.id,
    this.posicion = 0,
    this.tipo = TipoBloque.explicacion,
    this.cuerpo = '',
    this.carga = const <String, dynamic>{},
    this.origen = OrigenContenido.material,
    this.reportado = false,
    this.motivoReporte,
    this.procedencia = const <Procedencia>[],
    this.pregunta,
  });

  /// Lee `LessonBlockOut`.
  factory BloqueLeccion.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> carga = _mapa(json['payload']);
    return BloqueLeccion(
      id: _txt(_alguna(json, <String>['id', 'block_id'])),
      posicion: _ent(json['position']),
      tipo: TipoBloque.desdeApi(_alguna(json, <String>['block_type', 'type'])),
      cuerpo: _txt(_alguna(json, <String>['body', 'text', 'content'])),
      carga: carga,
      origen: OrigenContenido.desdeApi(json['origin']),
      reportado: _bol(json['is_flagged']),
      motivoReporte: _txtN(json['flag_reason']),
      procedencia: _lista(json['provenance'], Procedencia.desdeJson),
      pregunta:
          json['question'] is Map ? Pregunta.desdeJson(_mapa(json['question'])) : null,
    );
  }

  /// Identificador del bloque.
  final String id;

  /// Orden de presentación dentro de la lección.
  final int posicion;

  /// Tipo de bloque, que decide cómo se pinta.
  final TipoBloque tipo;

  /// Markdown restringido del cuerpo.
  final String cuerpo;

  /// Extras del bloque (`language`, `mermaid`, `question_id`).
  final Map<String, dynamic> carga;

  /// Respaldo del bloque.
  final OrigenContenido origen;

  /// ¿El usuario o la revisión automática lo reportaron?
  final bool reportado;

  /// Motivo del reporte.
  final String? motivoReporte;

  /// Citas de procedencia del bloque.
  final List<Procedencia> procedencia;

  /// Pregunta intercalada, cuando el servidor la envía completa.
  final Pregunta? pregunta;

  /// Lenguaje del bloque de código.
  String get lenguaje => _txt(carga['language'], 'sql');

  /// Definición Mermaid del diagrama.
  String? get diagrama => _txtN(carga['mermaid'] ?? carga['diagram']);

  /// Identificador de la pregunta intercalada.
  String? get preguntaId => pregunta?.id ?? _txtN(carga['question_id']);

  /// ¿El bloque viene del material del usuario?
  bool get esDelMaterial => origen == OrigenContenido.material;
}

/// Lección completa con bloques y procedencia (`LessonOut`).
class Leccion {
  const Leccion({
    required this.id,
    this.titulo = '',
    this.resumen,
    this.temaId,
    this.tituloTema,
    this.moduloId,
    this.tituloModulo,
    this.rutaId,
    this.tituloRuta,
    this.areaConocimientoId,
    this.posicion = 0,
    this.segundosEstimados = 540,
    this.estadoContenido = EstadoContenido.pendiente,
    this.origen = OrigenContenido.material,
    this.contenidoEscaso = false,
    this.cobertura = const <ObjetivoCobertura>[],
    this.bloques = const <BloqueLeccion>[],
    this.procedencia = const <Procedencia>[],
    this.preguntas = const <Pregunta>[],
    this.totalPreguntas = 0,
    this.estado = EstadoProgreso.sinEmpezar,
    this.ultimoPaso = 0,
    this.vecesCompletada = 0,
    this.versionContenido = 1,
  });

  /// Lee `{lesson, blocks[], provenance[], questions_preview[]}`.
  factory Leccion.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> m =
        json['lesson'] is Map ? _mapa(json['lesson']) : json;
    final List<BloqueLeccion> bloques = _lista(
      _alguna(json, <String>['blocks', 'lesson_blocks']),
      BloqueLeccion.desdeJson,
    )..sort((BloqueLeccion a, BloqueLeccion b) => a.posicion.compareTo(b.posicion));
    return Leccion(
      id: _txt(_alguna(m, <String>['id', 'lesson_id'])),
      titulo: _txt(m['title']),
      resumen: _txtN(m['summary']),
      temaId: _txtN(m['topic_id']),
      tituloTema: _txtN(_alguna(m, <String>['topic_title', 'topic_name'])),
      moduloId: _txtN(m['module_id']),
      tituloModulo: _txtN(_alguna(m, <String>['module_title', 'module_name'])),
      rutaId: _txtN(_alguna(m, <String>['learning_path_id', 'path_id'])),
      tituloRuta: _txtN(_alguna(m, <String>['path_title', 'path_name'])),
      areaConocimientoId: _txtN(m['knowledge_area_id']),
      posicion: _ent(m['position']),
      segundosEstimados: _ent(m['estimated_seconds'], 540),
      estadoContenido: EstadoContenido.desdeApi(m['content_status']),
      origen: OrigenContenido.desdeApi(m['origin']),
      contenidoEscaso: _bol(m['is_low_content']),
      cobertura: _lista(m['coverage_report'], ObjetivoCobertura.desdeJson),
      bloques: List<BloqueLeccion>.unmodifiable(bloques),
      procedencia: _lista(json['provenance'], Procedencia.desdeJson),
      preguntas: _lista(
        _alguna(json, <String>['questions_preview', 'questions']),
        Pregunta.desdeJson,
      ),
      totalPreguntas: _ent(m['question_count']),
      estado: EstadoProgreso.desdeApi(_alguna(m, <String>['state', 'progress_state'])),
      ultimoPaso: _ent(_alguna(m, <String>['last_step', 'last_block_index'])),
      vecesCompletada: _ent(m['completion_count']),
      versionContenido: _ent(m['content_version'], 1),
    );
  }

  /// Identificador de la lección.
  final String id;

  /// Título.
  final String titulo;

  /// Síntesis de cierre.
  final String? resumen;

  /// Tema al que pertenece.
  final String? temaId;

  /// Título del tema (miga de pan).
  final String? tituloTema;

  /// Módulo al que pertenece.
  final String? moduloId;

  /// Título del módulo (miga de pan).
  final String? tituloModulo;

  /// Ruta a la que pertenece.
  final String? rutaId;

  /// Título de la Ruta (miga de pan).
  final String? tituloRuta;

  /// Conocimiento asociado.
  final String? areaConocimientoId;

  /// Orden dentro del tema.
  final int posicion;

  /// Duración estimada en segundos.
  final int segundosEstimados;

  /// Estado de generación del contenido.
  final EstadoContenido estadoContenido;

  /// Respaldo documental de la lección.
  final OrigenContenido origen;

  /// Material insuficiente: el servidor paga la mitad de XP y oro.
  final bool contenidoEscaso;

  /// Cobertura por objetivo declarado.
  final List<ObjetivoCobertura> cobertura;

  /// Bloques ya ordenados por posición.
  final List<BloqueLeccion> bloques;

  /// Citas de procedencia de la lección.
  final List<Procedencia> procedencia;

  /// Preguntas de vista previa (sin claves de corrección).
  final List<Pregunta> preguntas;

  /// Preguntas asociadas según el servidor.
  final int totalPreguntas;

  /// Progreso del usuario en esta lección.
  final EstadoProgreso estado;

  /// Último bloque visto, para reanudar donde quedó.
  final int ultimoPaso;

  /// Veces que ya la completó.
  final int vecesCompletada;

  /// Versión del contenido generado.
  final int versionContenido;

  /// Minutos estimados, redondeados hacia arriba.
  int get minutosEstimados => (segundosEstimados / 60).ceil();

  /// Miga de pan "Ruta › Módulo › Tema".
  String get migaDePan {
    final List<String> partes = <String>[];
    final String? ruta = tituloRuta;
    final String? modulo = tituloModulo;
    final String? tema = tituloTema;
    if (ruta != null && ruta.isNotEmpty) partes.add(ruta);
    if (modulo != null && modulo.isNotEmpty) partes.add(modulo);
    if (tema != null && tema.isNotEmpty) partes.add(tema);
    return partes.join(' › ');
  }

  /// ¿Se puede abrir ya?
  bool get estaLista => estadoContenido.estaDisponible;

  /// ¿Es una repetición de una lección ya completada?
  bool get esRepaso => vecesCompletada > 0;

  /// Documentos citados, sin repetir, para la fila "Generado a partir de".
  List<String> get documentosCitados {
    final List<String> salida = <String>[];
    final List<Procedencia> todas = <Procedencia>[...procedencia];
    for (final BloqueLeccion b in bloques) {
      todas.addAll(b.procedencia);
    }
    for (final Procedencia p in todas) {
      final String? titulo = p.tituloDocumento;
      if (titulo != null && titulo.isNotEmpty && !salida.contains(titulo)) {
        salida.add(titulo);
      }
    }
    return salida;
  }
}

/// Actividad abierta con sus preguntas sin claves (`ActivityOut`).
class Actividad {
  const Actividad({
    required this.id,
    this.tipo = TipoActividad.leccion,
    this.contexto = ContextoActividad.leccion,
    this.preguntas = const <Pregunta>[],
    this.expiraEn,
    this.leccionId,
    this.temaId,
    this.moduloId,
    this.rutaId,
    this.areaConocimientoId,
    this.segundosActivos = 0,
    this.tituloTema,
  });

  /// Lee `{activity_id, questions[], expires_at}`.
  factory Actividad.desdeJson(Map<String, dynamic> json) {
    final List<Pregunta> preguntas = _lista(json['questions'], Pregunta.desdeJson);
    return Actividad(
      id: _txt(_alguna(json, <String>['activity_id', 'id'])),
      tipo: TipoActividad.desdeApi(json['activity_type']),
      contexto: ContextoActividad.desdeApi(json['context']),
      preguntas: List<Pregunta>.unmodifiable(preguntas),
      expiraEn: fechaHora(json['expires_at']),
      leccionId: _txtN(json['lesson_id']),
      temaId: _txtN(json['topic_id']),
      moduloId: _txtN(json['module_id']),
      rutaId: _txtN(_alguna(json, <String>['learning_path_id', 'path_id'])),
      areaConocimientoId: _txtN(json['knowledge_area_id']),
      segundosActivos: _ent(json['active_seconds']),
      tituloTema: _txtN(_alguna(json, <String>['topic_title', 'title'])),
    );
  }

  /// Identificador de la actividad abierta.
  final String id;

  /// Lección, práctica, repaso, desafío o evaluación.
  final TipoActividad tipo;

  /// Contexto que pondera el dominio.
  final ContextoActividad contexto;

  /// Preguntas presentadas, en orden.
  final List<Pregunta> preguntas;

  /// Cuándo caduca el intento (2 h por defecto).
  final DateTime? expiraEn;

  /// Lección de origen.
  final String? leccionId;

  /// Tema evaluado.
  final String? temaId;

  /// Módulo al que pertenece.
  final String? moduloId;

  /// Ruta a la que pertenece.
  final String? rutaId;

  /// Conocimiento asociado.
  final String? areaConocimientoId;

  /// Tiempo efectivo ya acumulado.
  final int segundosActivos;

  /// Título del tema, para el encabezado del repaso.
  final String? tituloTema;

  /// Cuántas preguntas trae.
  int get total => preguntas.length;

  /// ¿El intento ya venció?
  bool get vencio {
    final DateTime? limite = expiraEn;
    return limite != null && DateTime.now().isAfter(limite);
  }
}

/// Corrección de una respuesta con su retroalimentación (`AnswerResultOut`).
class ResultadoRespuesta {
  const ResultadoRespuesta({
    this.resultado = ResultadoIntento.incorrecta,
    this.esCorrecta = false,
    this.puntajeParcial = 0,
    this.xpOtorgado = 0,
    this.explicacion,
    this.respuestaCorrecta,
    this.procedencia = const <Procedencia>[],
    this.metodo = MetodoEvaluacion.determinista,
    this.retroalimentacion,
    this.salidaSandbox,
    this.preguntaId,
    this.indice,
    this.total,
  });

  /// Lee `AnswerResultOut`.
  factory ResultadoRespuesta.desdeJson(Map<String, dynamic> json) =>
      ResultadoRespuesta(
        resultado: ResultadoIntento.desdeApi(json['result']),
        esCorrecta: _bol(json['is_correct']),
        puntajeParcial: _dec(json['partial_score']),
        xpOtorgado: _ent(json['xp_awarded']),
        explicacion: _txtN(json['explanation']),
        respuestaCorrecta: json['correct_answer'],
        procedencia: _lista(
          _alguna(json, <String>['provenance', 'citations']),
          Procedencia.desdeJson,
        ),
        metodo: MetodoEvaluacion.desdeApi(json['evaluation_method']),
        retroalimentacion:
            _txtN(_alguna(json, <String>['feedback', 'judge_feedback'])),
        salidaSandbox: _txtN(_alguna(json, <String>['sandbox_output', 'output'])),
        preguntaId: _txtN(json['question_id']),
        indice: _entN(json['index']),
        total: _entN(json['total']),
      );

  /// Resultado normalizado de la respuesta.
  final ResultadoIntento resultado;

  /// Atajo booleano para la animación de acierto.
  final bool esCorrecta;

  /// Crédito parcial 0–100 (relacionar, ordenar, abierta).
  final double puntajeParcial;

  /// XP que pagó esta respuesta, ya calculado por el servidor.
  final int xpOtorgado;

  /// Explicación que se muestra tras responder.
  final String? explicacion;

  /// Respuesta correcta tal cual la envía el servidor (forma libre).
  final Object? respuestaCorrecta;

  /// Citas del material que respaldan la corrección.
  final List<Procedencia> procedencia;

  /// Cómo se corrigió.
  final MetodoEvaluacion metodo;

  /// Comentario del juez o de la rúbrica.
  final String? retroalimentacion;

  /// Salida de la ejecución en sandbox del ejercicio SQL.
  final String? salidaSandbox;

  /// Pregunta corregida.
  final String? preguntaId;

  /// Posición dentro de la actividad, si el servidor la envía.
  final int? indice;

  /// Total de preguntas de la actividad.
  final int? total;

  /// ¿Hubo crédito parcial?
  bool get esParcial => resultado == ResultadoIntento.parcial;

  /// ¿Quedó pendiente de la revisión del juez?
  bool get estaPendiente =>
      resultado == ResultadoIntento.porRevisar ||
      metodo == MetodoEvaluacion.pendiente;

  /// Respuesta correcta en texto legible, con listas separadas por comas.
  String get respuestaCorrectaTexto {
    final Object? v = respuestaCorrecta;
    if (v == null) return '';
    if (v is String) return v;
    if (v is List) return v.map((Object? e) => e?.toString() ?? '').join(', ');
    if (v is Map) {
      return v.values.map((Object? e) => e?.toString() ?? '').join(', ');
    }
    return v.toString();
  }
}

/// Repaso recomendado de un tema en riesgo (`ReviewSuggestionOut`).
class SugerenciaRepaso {
  const SugerenciaRepaso({
    required this.temaId,
    this.titulo = '',
    this.areaConocimientoId,
    this.nombreConocimiento,
    this.dominio = 0,
    this.estado = EstadoDominio.sinEvidencia,
    this.minutosEstimados = 5,
    this.preguntas = 0,
    this.motivo,
    this.rutaId,
    this.moduloId,
    this.ultimaPracticaEn,
  });

  /// Lee `ReviewSuggestionOut`.
  factory SugerenciaRepaso.desdeJson(Map<String, dynamic> json) => SugerenciaRepaso(
        temaId: _txt(_alguna(json, <String>['topic_id', 'id'])),
        titulo: _txt(_alguna(json, <String>['title', 'topic_title', 'name'])),
        areaConocimientoId: _txtN(json['knowledge_area_id']),
        nombreConocimiento:
            _txtN(_alguna(json, <String>['knowledge_area_name', 'area_name'])),
        dominio: _dec(_alguna(json, <String>['mastery', 'mastery_pct'])),
        estado: EstadoDominio.desdeApi(json['status']),
        minutosEstimados: _ent(
          _alguna(json, <String>['estimated_minutes', 'duration_minutes']),
          5,
        ),
        preguntas: _ent(_alguna(json, <String>['question_count', 'questions'])),
        motivo: _txtN(_alguna(json, <String>['reason', 'reason_text'])),
        rutaId: _txtN(_alguna(json, <String>['learning_path_id', 'path_id'])),
        moduloId: _txtN(json['module_id']),
        ultimaPracticaEn: fechaHora(json['last_practiced_at']),
      );

  /// Tema que conviene repasar.
  final String temaId;

  /// Título del tema.
  final String titulo;

  /// Conocimiento al que pertenece.
  final String? areaConocimientoId;

  /// Nombre del conocimiento.
  final String? nombreConocimiento;

  /// Dominio actual del tema (0–100).
  final double dominio;

  /// Estado de dominio que motiva el repaso.
  final EstadoDominio estado;

  /// Duración estimada del repaso.
  final int minutosEstimados;

  /// Preguntas que traerá el repaso (4–8).
  final int preguntas;

  /// Por qué se recomienda, en palabras del servidor.
  final String? motivo;

  /// Ruta de origen.
  final String? rutaId;

  /// Módulo de origen.
  final String? moduloId;

  /// Última vez que lo practicó.
  final DateTime? ultimaPracticaEn;

  /// ¿El tema está en riesgo o debilitado?
  bool get esUrgente => estado.pideRepaso;
}

/// Re-explicación alternativa generada por IA (`ExplanationOut`).
class Explicacion {
  const Explicacion({
    this.enfoque = '',
    this.cuerpo = '',
    this.citas = const <Procedencia>[],
    this.temaId,
  });

  /// Lee `{approach, body, citations[]}`.
  factory Explicacion.desdeJson(Map<String, dynamic> json) => Explicacion(
        enfoque: _txt(_alguna(json, <String>['approach', 'style'])),
        cuerpo: _txt(_alguna(json, <String>['body', 'text', 'content'])),
        citas: _lista(
          _alguna(json, <String>['citations', 'provenance']),
          Procedencia.desdeJson,
        ),
        temaId: _txtN(json['topic_id']),
      );

  /// Enfoque usado (analogía, paso a paso, ejemplo…).
  final String enfoque;

  /// Texto de la explicación, en markdown restringido.
  final String cuerpo;

  /// Citas del material que la respaldan.
  final List<Procedencia> citas;

  /// Tema re-explicado.
  final String? temaId;
}

/// Tiempo efectivo acumulado que devuelve el latido de la actividad.
class LatidoActividad {
  const LatidoActividad({this.segundosActivos = 0});

  /// Lee `{"active_seconds": 320}`.
  factory LatidoActividad.desdeJson(Map<String, dynamic> json) =>
      LatidoActividad(segundosActivos: _ent(json['active_seconds']));

  /// Tiempo efectivo validado por el servidor.
  final int segundosActivos;
}

// ---------------------------------------------------------------------------
// §7.7 Evaluación de módulo
// ---------------------------------------------------------------------------

/// Recompensa anunciada o ya otorgada, en su forma más simple.
class RecompensaSimple {
  const RecompensaSimple({
    this.xp = 0,
    this.oro = 0,
    this.tituloId,
    this.itemId,
    this.nombreItem,
    this.descripcion,
  });

  /// Lee `{xp, gold, title_id}` y sus variantes.
  factory RecompensaSimple.desdeJson(Map<String, dynamic> json) => RecompensaSimple(
        xp: _ent(_alguna(json, <String>['xp', 'xp_amount', 'reward_xp'])),
        oro: _ent(_alguna(json, <String>['gold', 'gold_amount', 'reward_gold'])),
        tituloId: _txtN(json['title_id']),
        itemId: _txtN(_alguna(json, <String>['item_id', 'reward_item_id'])),
        nombreItem: _txtN(_alguna(json, <String>['item_name', 'reward_item_name'])),
        descripcion: _txtN(_alguna(json, <String>['description', 'label'])),
      );

  /// Lee la recompensa aunque venga anidada bajo `reward` o `rewards`.
  static RecompensaSimple? desdeCampo(Object? valor) {
    final Map<String, dynamic>? m = _mapaN(valor);
    if (m == null) return null;
    return RecompensaSimple.desdeJson(m);
  }

  /// XP de bonificación.
  final int xp;

  /// Oro.
  final int oro;

  /// Título honorífico que concede, si lo hay.
  final String? tituloId;

  /// Ítem que entrega, si lo hay.
  final String? itemId;

  /// Nombre del ítem, para el chip.
  final String? nombreItem;

  /// Texto alternativo de la recompensa.
  final String? descripcion;

  /// ¿No entrega nada?
  bool get estaVacia => xp == 0 && oro == 0 && itemId == null && tituloId == null;

  /// Resumen legible: "+100 XP · +30 Oro".
  String get resumen {
    final List<String> partes = <String>[];
    if (xp > 0) partes.add('+$xp XP');
    if (oro > 0) partes.add('+$oro Oro');
    final String? item = nombreItem;
    if (item != null && item.isNotEmpty) partes.add(item);
    final String? extra = descripcion;
    if (partes.isEmpty && extra != null) partes.add(extra);
    return partes.join(' · ');
  }
}

/// Pantalla de entrada al Desafío del módulo (`AssessmentInfoOut`).
class InfoEvaluacion {
  const InfoEvaluacion({
    required this.evaluacion,
    this.intentosUsados = 0,
    this.enfriamientoHasta,
    this.puedeEmpezar = false,
    this.vistaPreviaRecompensa,
    this.motivoBloqueo,
    this.moduloId,
    this.tituloModulo,
    this.rutaId,
    this.reglas = const <String>[],
    this.mejorPuntaje,
    this.temas = const <String>[],
  });

  /// Lee `{assessment, attempts_used, cooldown_until, can_start, reward_preview}`.
  factory InfoEvaluacion.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> ev =
        json['assessment'] is Map ? _mapa(json['assessment']) : json;
    return InfoEvaluacion(
      evaluacion: ResumenEvaluacion.desdeJson(ev),
      intentosUsados: _ent(json['attempts_used']),
      enfriamientoHasta: fechaHora(json['cooldown_until']),
      puedeEmpezar: _bol(json['can_start'], true),
      vistaPreviaRecompensa: RecompensaSimple.desdeCampo(
        _alguna(json, <String>['reward_preview', 'reward']),
      ),
      motivoBloqueo: _txtN(_alguna(json, <String>['locked_reason', 'blocked_reason'])),
      moduloId: _txtN(json['module_id']),
      tituloModulo: _txtN(_alguna(json, <String>['module_title', 'module_name'])),
      rutaId: _txtN(_alguna(json, <String>['learning_path_id', 'path_id'])),
      reglas: _textos(json['rules']),
      mejorPuntaje: _decN(_alguna(json, <String>['best_score', 'best_score_pct'])),
      temas: _textos(_alguna(json, <String>['topic_titles', 'topics'])),
    );
  }

  /// Datos de la evaluación (preguntas, umbral, intentos por día).
  final ResumenEvaluacion evaluacion;

  /// Intentos ya usados hoy.
  final int intentosUsados;

  /// Hasta cuándo dura el enfriamiento tras reprobar.
  final DateTime? enfriamientoHasta;

  /// ¿Se puede empezar ahora?
  final bool puedeEmpezar;

  /// Recompensa anunciada, calculada por el servidor.
  final RecompensaSimple? vistaPreviaRecompensa;

  /// Por qué no se puede empezar, en palabras del servidor.
  final String? motivoBloqueo;

  /// Módulo evaluado.
  final String? moduloId;

  /// Título del módulo, para el encabezado.
  final String? tituloModulo;

  /// Ruta a la que pertenece.
  final String? rutaId;

  /// Reglas que se muestran antes de entrar.
  final List<String> reglas;

  /// Mejor puntaje histórico, si ya lo intentó.
  final double? mejorPuntaje;

  /// Temas que entran en el desafío.
  final List<String> temas;

  /// Intentos que aún quedan hoy.
  int get intentosRestantes {
    final int tope = evaluacion.intentosMaximosPorDia;
    final int restan = tope - intentosUsados;
    return restan < 0 ? 0 : restan;
  }

  /// ¿Sigue en enfriamiento?
  bool get enEnfriamiento {
    final DateTime? hasta = enfriamientoHasta;
    return hasta != null && hasta.isAfter(DateTime.now());
  }
}

/// Intento de evaluación recién creado (`AssessmentAttemptOut`).
class IntentoEvaluacion {
  const IntentoEvaluacion({
    required this.id,
    this.preguntas = const <Pregunta>[],
    this.totalPreguntas = 0,
    this.evaluacionId,
    this.moduloId,
    this.numeroIntento = 1,
    this.iniciadoEn,
    this.expiraEn,
    this.estado = EstadoIntento.enProgreso,
  });

  /// Lee `{attempt_id, questions[], question_count}`.
  factory IntentoEvaluacion.desdeJson(Map<String, dynamic> json) {
    final List<Pregunta> preguntas = _lista(json['questions'], Pregunta.desdeJson);
    return IntentoEvaluacion(
      id: _txt(_alguna(json, <String>['attempt_id', 'id'])),
      preguntas: List<Pregunta>.unmodifiable(preguntas),
      totalPreguntas: _ent(json['question_count'], preguntas.length),
      evaluacionId: _txtN(json['assessment_id']),
      moduloId: _txtN(json['module_id']),
      numeroIntento: _ent(json['attempt_no'], 1),
      iniciadoEn: fechaHora(json['started_at']),
      expiraEn: fechaHora(json['expires_at']),
      estado: EstadoIntento.desdeApi(json['status']),
    );
  }

  /// Identificador del intento.
  final String id;

  /// Preguntas muestreadas del banco.
  final List<Pregunta> preguntas;

  /// Cuántas preguntas presenta el intento.
  final int totalPreguntas;

  /// Evaluación a la que pertenece.
  final String? evaluacionId;

  /// Módulo evaluado.
  final String? moduloId;

  /// Número de intento (penaliza el dominio efectivo).
  final int numeroIntento;

  /// Inicio del intento, según el reloj del servidor.
  final DateTime? iniciadoEn;

  /// Caducidad del intento.
  final DateTime? expiraEn;

  /// Estado del intento.
  final EstadoIntento estado;
}

/// Acuse de recibo de una respuesta de evaluación (`{recorded, index, total}`).
class RegistroRespuesta {
  const RegistroRespuesta({
    this.registrada = false,
    this.indice = 0,
    this.total = 0,
    this.esCorrecta,
  });

  /// Lee `{"recorded": true, "index": 3, "total": 10}`.
  factory RegistroRespuesta.desdeJson(Map<String, dynamic> json) => RegistroRespuesta(
        registrada: _bol(json['recorded'], true),
        indice: _ent(json['index']),
        total: _ent(json['total']),
        esCorrecta: json['is_correct'] == null ? null : _bol(json['is_correct']),
      );

  /// ¿El servidor guardó la respuesta?
  final bool registrada;

  /// Posición de la pregunta respondida (1-based según el servidor).
  final int indice;

  /// Total de preguntas del intento.
  final int total;

  /// Retroalimentación mínima: acertó o no. Sin explicación.
  final bool? esCorrecta;

  /// Progreso del intento entre 0 y 1.
  double get fraccion => total <= 0 ? 0 : (indice / total).clamp(0, 1).toDouble();
}

/// Desglose de acierto por tema de un intento (`per_topic`).
class PuntajeTema {
  const PuntajeTema({
    required this.temaId,
    this.titulo = '',
    this.correctas = 0,
    this.total = 0,
    this.porcentaje = 0,
    this.esDebil = false,
  });

  /// Lee `{topic_id, correct, total, pct}`.
  factory PuntajeTema.desdeJson(Map<String, dynamic> json) {
    final int correctas = _ent(_alguna(json, <String>['correct', 'correct_count']));
    final int total = _ent(_alguna(json, <String>['total', 'question_count']));
    final double pct = _dec(
      _alguna(json, <String>['pct', 'score_pct', 'percentage']),
      total > 0 ? (correctas / total) * 100 : 0,
    );
    return PuntajeTema(
      temaId: _txt(_alguna(json, <String>['topic_id', 'id'])),
      titulo: _txt(_alguna(json, <String>['title', 'topic_title', 'name'])),
      correctas: correctas,
      total: total,
      porcentaje: pct,
      esDebil: _bol(json['is_weak'], pct < 60),
    );
  }

  /// Convierte un elemento que puede ser objeto o simplemente un id.
  static PuntajeTema desdeBruto(Object? bruto) {
    if (bruto is Map) {
      return PuntajeTema.desdeJson(Map<String, dynamic>.from(bruto));
    }
    return PuntajeTema(temaId: _txt(bruto), esDebil: true);
  }

  /// Tema evaluado.
  final String temaId;

  /// Título del tema.
  final String titulo;

  /// Aciertos en este tema.
  final int correctas;

  /// Preguntas de este tema en el intento.
  final int total;

  /// Porcentaje de acierto.
  final double porcentaje;

  /// ¿Quedó por debajo del umbral de debilidad?
  final bool esDebil;

  /// Progreso entre 0 y 1 para la barra.
  double get fraccion => (porcentaje / 100).clamp(0, 1).toDouble();
}

/// Resultado de un intento de evaluación (`assessment_result` del recibo).
class ResultadoEvaluacionModulo {
  const ResultadoEvaluacionModulo({
    this.puntaje = 0,
    this.resultado = ResultadoEvaluacion.reprobado,
    this.porTema = const <PuntajeTema>[],
    this.temasDebiles = const <PuntajeTema>[],
    this.enfriamientoHasta,
    this.sugerenciasRepaso = const <SugerenciaRepaso>[],
    this.correctas = 0,
    this.total = 0,
    this.puntajeAprobacion = 70,
    this.numeroIntento = 1,
    this.puntajeEfectivo,
    this.moduloId,
    this.evaluacionId,
  });

  /// Lee `{score_pct, outcome, per_topic[], weak_topics[], cooldown_until, …}`.
  factory ResultadoEvaluacionModulo.desdeJson(Map<String, dynamic> json) {
    final Object? debiles = _alguna(json, <String>['weak_topics', 'weak_topic_ids']);
    final List<PuntajeTema> listaDebiles = <PuntajeTema>[];
    if (debiles is List) {
      for (final Object? bruto in debiles) {
        listaDebiles.add(PuntajeTema.desdeBruto(bruto));
      }
    }
    return ResultadoEvaluacionModulo(
      puntaje: _dec(_alguna(json, <String>['score_pct', 'score'])),
      resultado: ResultadoEvaluacion.desdeApi(json['outcome']),
      porTema: _lista(
        _alguna(json, <String>['per_topic', 'per_topic_scores']),
        PuntajeTema.desdeJson,
      ),
      temasDebiles: List<PuntajeTema>.unmodifiable(listaDebiles),
      enfriamientoHasta: fechaHora(json['cooldown_until']),
      sugerenciasRepaso: _lista(
        json['review_suggestions'],
        SugerenciaRepaso.desdeJson,
      ),
      correctas: _ent(_alguna(json, <String>['correct_count', 'correct'])),
      total: _ent(_alguna(json, <String>['question_count', 'total'])),
      puntajeAprobacion: _dec(json['pass_score'], 70),
      numeroIntento: _ent(json['attempt_no'], 1),
      puntajeEfectivo: _decN(json['effective_score']),
      moduloId: _txtN(json['module_id']),
      evaluacionId: _txtN(json['assessment_id']),
    );
  }

  /// Puntaje 0–100 calculado por el servidor.
  final double puntaje;

  /// Resultado final del intento.
  final ResultadoEvaluacion resultado;

  /// Desglose por tema.
  final List<PuntajeTema> porTema;

  /// Temas por debajo del umbral en este intento.
  final List<PuntajeTema> temasDebiles;

  /// Enfriamiento hasta el próximo intento.
  final DateTime? enfriamientoHasta;

  /// Repasos sugeridos para levantar los temas débiles.
  final List<SugerenciaRepaso> sugerenciasRepaso;

  /// Aciertos del intento.
  final int correctas;

  /// Preguntas del intento.
  final int total;

  /// Umbral de aprobación vigente.
  final double puntajeAprobacion;

  /// Número de intento.
  final int numeroIntento;

  /// Puntaje con penalización por reintento.
  final double? puntajeEfectivo;

  /// Módulo evaluado.
  final String? moduloId;

  /// Evaluación rendida.
  final String? evaluacionId;

  /// ¿Superó el umbral?
  bool get aprobo => resultado.aprobo;

  /// Progreso entre 0 y 1 para el anillo de puntaje.
  double get fraccion => (puntaje / 100).clamp(0, 1).toDouble();
}

/// Una respuesta del intento, ya revisada (`AssessmentReviewOut.answers`).
class RespuestaRevisada {
  const RespuestaRevisada({
    required this.pregunta,
    this.respuesta,
    this.resultado = ResultadoIntento.incorrecta,
    this.esCorrecta = false,
    this.puntajeParcial = 0,
    this.explicacion,
    this.respuestaCorrecta,
    this.procedencia = const <Procedencia>[],
    this.metodo = MetodoEvaluacion.determinista,
    this.indice = 0,
  });

  /// Lee una fila de la revisión, con la pregunta anidada o en el mismo mapa.
  factory RespuestaRevisada.desdeJson(Map<String, dynamic> json) => RespuestaRevisada(
        pregunta: Pregunta.desdeJson(
          json['question'] is Map ? _mapa(json['question']) : json,
        ),
        respuesta: _alguna(json, <String>['response', 'answer', 'user_answer']),
        resultado: ResultadoIntento.desdeApi(json['result']),
        esCorrecta: _bol(json['is_correct']),
        puntajeParcial: _dec(json['partial_score']),
        explicacion: _txtN(json['explanation']),
        respuestaCorrecta: json['correct_answer'],
        procedencia: _lista(
          _alguna(json, <String>['provenance', 'citations']),
          Procedencia.desdeJson,
        ),
        metodo: MetodoEvaluacion.desdeApi(json['evaluation_method']),
        indice: _ent(_alguna(json, <String>['index', 'position'])),
      );

  /// Pregunta revisada, ya con su explicación.
  final Pregunta pregunta;

  /// Lo que respondió el usuario.
  final Object? respuesta;

  /// Resultado normalizado.
  final ResultadoIntento resultado;

  /// Atajo de acierto.
  final bool esCorrecta;

  /// Crédito parcial obtenido.
  final double puntajeParcial;

  /// Explicación de la corrección.
  final String? explicacion;

  /// Respuesta correcta según el servidor.
  final Object? respuestaCorrecta;

  /// Citas del material.
  final List<Procedencia> procedencia;

  /// Cómo se corrigió.
  final MetodoEvaluacion metodo;

  /// Posición dentro del intento.
  final int indice;
}

/// Revisión completa de un intento de evaluación (`AssessmentReviewOut`).
class RevisionEvaluacion {
  const RevisionEvaluacion({
    required this.id,
    this.estado = EstadoIntento.enviado,
    this.resultado,
    this.respuestas = const <RespuestaRevisada>[],
    this.enviadoEn,
    this.iniciadoEn,
    this.tituloModulo,
    this.moduloId,
  });

  /// Lee `AssessmentReviewOut`.
  factory RevisionEvaluacion.desdeJson(Map<String, dynamic> json) {
    final List<RespuestaRevisada> respuestas = _lista(
      _alguna(json, <String>['answers', 'question_attempts', 'items']),
      RespuestaRevisada.desdeJson,
    )..sort(
        (RespuestaRevisada a, RespuestaRevisada b) => a.indice.compareTo(b.indice),
      );
    final Map<String, dynamic>? resumen = _mapaN(json['result']);
    return RevisionEvaluacion(
      id: _txt(_alguna(json, <String>['attempt_id', 'id'])),
      estado: EstadoIntento.desdeApi(json['status']),
      resultado: ResultadoEvaluacionModulo.desdeJson(resumen ?? json),
      respuestas: List<RespuestaRevisada>.unmodifiable(respuestas),
      enviadoEn: fechaHora(json['submitted_at']),
      iniciadoEn: fechaHora(json['started_at']),
      tituloModulo: _txtN(_alguna(json, <String>['module_title', 'module_name'])),
      moduloId: _txtN(json['module_id']),
    );
  }

  /// Identificador del intento revisado.
  final String id;

  /// Estado del intento.
  final EstadoIntento estado;

  /// Puntaje y desglose del intento.
  final ResultadoEvaluacionModulo? resultado;

  /// Respuestas, en el orden en que se presentaron.
  final List<RespuestaRevisada> respuestas;

  /// Cuándo se envió.
  final DateTime? enviadoEn;

  /// Cuándo empezó.
  final DateTime? iniciadoEn;

  /// Título del módulo evaluado.
  final String? tituloModulo;

  /// Módulo evaluado.
  final String? moduloId;

  /// Respuestas falladas, para el filtro "Ver solo las falladas".
  List<RespuestaRevisada> get falladas => respuestas
      .where((RespuestaRevisada r) => !r.esCorrecta)
      .toList(growable: false);
}

// ---------------------------------------------------------------------------
// §7.8 Panel principal, perfil y estadísticas
// ---------------------------------------------------------------------------

/// Próximo hito de racha con su recompensa (`next_milestone`).
class HitoRacha {
  const HitoRacha({
    this.dias = 0,
    this.faltan = 0,
    this.recompensa,
    this.titulo,
  });

  /// Lee `{days, remaining, reward}`.
  factory HitoRacha.desdeJson(Map<String, dynamic> json) => HitoRacha(
        dias: _ent(_alguna(json, <String>['days', 'target', 'milestone'])),
        faltan: _ent(_alguna(json, <String>['remaining', 'days_remaining'])),
        recompensa: RecompensaSimple.desdeCampo(
          _alguna(json, <String>['reward', 'rewards']),
        ),
        titulo: _txtN(_alguna(json, <String>['title', 'name', 'achievement_name'])),
      );

  /// Días de racha que exige el hito.
  final int dias;

  /// Cuántos días faltan para alcanzarlo.
  final int faltan;

  /// Qué entrega al llegar.
  final RecompensaSimple? recompensa;

  /// Nombre del hito o del logro asociado.
  final String? titulo;
}

/// Estado de la racha del usuario (`StreakOut` y `dashboard.streak`).
class Racha {
  const Racha({
    this.actual = 0,
    this.mejor = 0,
    this.estado,
    this.estadoDia = EstadoDia.inactivo,
    this.totalDiasActivos = 0,
    this.graciaDisponible = false,
    this.proximoHito,
    this.ultimoCambio,
    this.rachaAnterior = 0,
    this.ultimaFechaActiva,
    this.iniciadaEl,
  });

  /// Lee `StreakOut` y el bloque `streak` del panel.
  factory Racha.desdeJson(Map<String, dynamic> json) => Racha(
        actual: _ent(_alguna(json, <String>['current', 'current_length'])),
        mejor: _ent(_alguna(json, <String>['best', 'best_length'])),
        estado: _txtN(json['status']),
        estadoDia: EstadoDia.desdeApi(json['day_status']),
        totalDiasActivos: _ent(json['total_active_days']),
        graciaDisponible: _bol(json['grace_available']),
        proximoHito: json['next_milestone'] is Map
            ? HitoRacha.desdeJson(_mapa(json['next_milestone']))
            : null,
        ultimoCambio: desdeClaveApiOpcional(
          CambioRacha.values,
          _alguna(json, <String>['last_change', 'change']),
        ),
        rachaAnterior: _ent(json['previous_length']),
        ultimaFechaActiva: fechaDia(json['last_active_date']),
        iniciadaEl: fechaDia(json['started_on']),
      );

  /// Días consecutivos activos.
  final int actual;

  /// Mejor racha histórica; nunca disminuye.
  final int mejor;

  /// Estado textual que envía el servidor (`active`, `at_risk`…).
  final String? estado;

  /// Estado del día de hoy.
  final EstadoDia estadoDia;

  /// Días activos de por vida.
  final int totalDiasActivos;

  /// ¿Queda día de gracia este mes?
  final bool graciaDisponible;

  /// Próximo hito y su recompensa.
  final HitoRacha? proximoHito;

  /// Motivo del último cambio.
  final CambioRacha? ultimoCambio;

  /// Longitud de la racha anterior ("Tu mejor marca sigue siendo 12 días").
  final int rachaAnterior;

  /// Última fecha local activa.
  final DateTime? ultimaFechaActiva;

  /// Día en que empezó la racha vigente.
  final DateTime? iniciadaEl;

  /// ¿Hoy ya cuenta para la racha?
  bool get hoyCuenta => estadoDia.cuentaParaRacha;

  /// ¿Todavía no ha empezado ninguna racha?
  bool get estaVacia => actual == 0 && mejor == 0;
}

/// Un día del calendario de racha (`StreakCalendarOut.days[]`).
class DiaRacha {
  const DiaRacha({
    required this.fecha,
    this.estadoDia = EstadoDia.inactivo,
    this.objetivoCumplido = false,
    this.xpEducativo = 0,
    this.minutos = 0,
    this.actividades = 0,
  });

  /// Lee `{date, day_status, goal_met, educational_xp, minutes, activities}`.
  factory DiaRacha.desdeJson(Map<String, dynamic> json) => DiaRacha(
        fecha: fechaDia(_alguna(json, <String>['date', 'local_date'])) ??
            DateTime(1970),
        estadoDia: EstadoDia.desdeApi(_alguna(json, <String>['day_status', 'status'])),
        objetivoCumplido: _bol(json['goal_met']),
        xpEducativo: _ent(_alguna(json, <String>['educational_xp', 'xp'])),
        minutos: _ent(json['minutes']),
        actividades: _ent(_alguna(json, <String>['activities', 'activity_units'])),
      );

  /// Día local al que se refiere.
  final DateTime fecha;

  /// Estado del día.
  final EstadoDia estadoDia;

  /// ¿Se cumplió el objetivo diario ese día?
  final bool objetivoCumplido;

  /// XP educativo del día.
  final int xpEducativo;

  /// Minutos efectivos del día.
  final int minutos;

  /// Actividades completadas.
  final int actividades;

  /// ¿El día cuenta para la racha?
  bool get cuenta => estadoDia.cuentaParaRacha;
}

/// Calendario mensual de la racha (`StreakCalendarOut`).
class CalendarioRacha {
  const CalendarioRacha({
    this.mes = '',
    this.dias = const <DiaRacha>[],
    this.diasActivos = 0,
    this.mejorLongitud = 0,
  });

  /// Lee `{month, days[], active_days, best_length}`.
  factory CalendarioRacha.desdeJson(Map<String, dynamic> json) => CalendarioRacha(
        mes: _txt(json['month']),
        dias: _lista(json['days'], DiaRacha.desdeJson),
        diasActivos: _ent(json['active_days']),
        mejorLongitud: _ent(json['best_length']),
      );

  /// Mes en formato `2026-09`.
  final String mes;

  /// Días del mes con su estado.
  final List<DiaRacha> dias;

  /// Días activos del mes.
  final int diasActivos;

  /// Mejor racha alcanzada dentro del mes.
  final int mejorLongitud;

  /// Busca el estado de un día concreto.
  DiaRacha? porFecha(DateTime dia) {
    for (final DiaRacha d in dias) {
      if (d.fecha.year == dia.year &&
          d.fecha.month == dia.month &&
          d.fecha.day == dia.day) {
        return d;
      }
    }
    return null;
  }
}

/// Recomendación adaptativa del objetivo diario (`daily_goals.recommendation`).
class RecomendacionObjetivo {
  const RecomendacionObjetivo({
    this.direccion = '',
    this.tipoSugerido = TipoObjetivo.minutos,
    this.metaSugerida = 0,
    this.calculadaEl,
    this.mensaje,
  });

  /// Lee `{direction, suggested_type, suggested_target, computed_on}`.
  factory RecomendacionObjetivo.desdeJson(Map<String, dynamic> json) =>
      RecomendacionObjetivo(
        direccion: _txt(json['direction']),
        tipoSugerido: TipoObjetivo.desdeApi(json['suggested_type']),
        metaSugerida: _ent(json['suggested_target']),
        calculadaEl: fechaDia(json['computed_on']),
        mensaje: _txtN(_alguna(json, <String>['message', 'text'])),
      );

  /// `up` para subir la meta, `down` para bajarla.
  final String direccion;

  /// Tipo de objetivo propuesto.
  final TipoObjetivo tipoSugerido;

  /// Meta propuesta.
  final int metaSugerida;

  /// Día en que se calculó.
  final DateTime? calculadaEl;

  /// Texto que acompaña la propuesta.
  final String? mensaje;

  /// ¿Propone subir el listón?
  bool get proponeSubir => direccion.toLowerCase().startsWith('up');

  /// ¿Hay algo que proponer?
  bool get esValida => metaSugerida > 0;
}

/// Objetivo diario vigente con su progreso (`DailyGoalOut`).
class ObjetivoDiario {
  const ObjetivoDiario({
    this.tipo = TipoObjetivo.minutos,
    this.meta = 20,
    this.progreso = 0,
    this.cumplido = false,
    this.oroBonus = 0,
    this.vigenteDesde,
    this.tipoPendiente,
    this.metaPendiente,
    this.pendienteDesde,
    this.recomendacion,
    this.cumplidoEn,
    this.reciensCumplido = false,
  });

  /// Lee `DailyGoalOut` y el bloque `daily_goal` del panel o del recibo.
  factory ObjetivoDiario.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic>? reco = _mapaN(json['recommendation']);
    final RecomendacionObjetivo? recomendacion =
        reco == null || reco.isEmpty ? null : RecomendacionObjetivo.desdeJson(reco);
    return ObjetivoDiario(
      tipo: TipoObjetivo.desdeApi(_alguna(json, <String>['type', 'goal_type'])),
      meta: _ent(_alguna(json, <String>['target', 'goal_target']), 20),
      progreso: _ent(_alguna(json, <String>['progress', 'goal_progress'])),
      cumplido: _bol(_alguna(json, <String>['met', 'goal_met'])),
      oroBonus: _ent(json['bonus_gold']),
      vigenteDesde: fechaDia(json['effective_from']),
      tipoPendiente: desdeClaveApiOpcional(TipoObjetivo.values, json['pending_type']),
      metaPendiente: _entN(json['pending_target']),
      pendienteDesde: fechaDia(json['pending_from']),
      recomendacion: recomendacion != null && recomendacion.esValida
          ? recomendacion
          : null,
      cumplidoEn: fechaHora(json['goal_met_at']),
      reciensCumplido: _bol(json['just_met']),
    );
  }

  /// Tipo de objetivo vigente.
  final TipoObjetivo tipo;

  /// Meta del día.
  final int meta;

  /// Avance de hoy en la unidad del objetivo.
  final int progreso;

  /// ¿Ya está cumplido?
  final bool cumplido;

  /// Oro de bonificación por cumplirlo, calculado por el servidor.
  final int oroBonus;

  /// Desde cuándo rige.
  final DateTime? vigenteDesde;

  /// Tipo programado para el día siguiente.
  final TipoObjetivo? tipoPendiente;

  /// Meta programada para el día siguiente.
  final int? metaPendiente;

  /// Cuándo entra en vigor el cambio programado.
  final DateTime? pendienteDesde;

  /// Recomendación adaptativa pendiente de responder.
  final RecomendacionObjetivo? recomendacion;

  /// Momento exacto en que se cumplió.
  final DateTime? cumplidoEn;

  /// ¿Se acaba de cumplir con esta acción? (solo en el recibo).
  final bool reciensCumplido;

  /// Progreso entre 0 y 1 para el anillo.
  double get fraccion =>
      meta <= 0 ? 0 : (progreso / meta).clamp(0, 1).toDouble();

  /// Cuánto falta en la unidad del objetivo.
  int get restante {
    final int falta = meta - progreso;
    return falta < 0 ? 0 : falta;
  }

  /// Texto de la meta ("20 minutos", "100 XP").
  String get metaLegible => '$meta ${tipo.unidad}';

  /// ¿Hay un cambio programado para mañana?
  bool get tieneCambioPendiente => metaPendiente != null || tipoPendiente != null;
}

/// Qué propone el botón "Continuar" del panel (`continue_action`).
class AccionContinuar {
  const AccionContinuar({
    this.tipo = TipoAccionContinuar.ninguna,
    this.rutaId,
    this.moduloId,
    this.leccionId,
    this.temaId,
    this.evaluacionId,
    this.titulo,
    this.migaDePan,
    this.vistaPreviaRecompensa,
    this.segundosEstimados = 0,
  });

  /// Lee `{type, path_id, module_id, lesson_id, title, breadcrumb, …}`.
  factory AccionContinuar.desdeJson(Map<String, dynamic> json) => AccionContinuar(
        tipo: TipoAccionContinuar.desdeApi(json['type']),
        rutaId: _txtN(_alguna(json, <String>['path_id', 'learning_path_id'])),
        moduloId: _txtN(json['module_id']),
        leccionId: _txtN(json['lesson_id']),
        temaId: _txtN(json['topic_id']),
        evaluacionId: _txtN(json['assessment_id']),
        titulo: _txtN(json['title']),
        migaDePan: _txtN(json['breadcrumb']),
        vistaPreviaRecompensa: RecompensaSimple.desdeCampo(
          _alguna(json, <String>['reward_preview', 'reward']),
        ),
        segundosEstimados: _ent(json['estimated_seconds']),
      );

  /// Qué hay que hacer a continuación.
  final TipoAccionContinuar tipo;

  /// Ruta implicada.
  final String? rutaId;

  /// Módulo implicado.
  final String? moduloId;

  /// Lección implicada.
  final String? leccionId;

  /// Tema implicado (repaso o práctica).
  final String? temaId;

  /// Evaluación implicada.
  final String? evaluacionId;

  /// Título de la actividad propuesta.
  final String? titulo;

  /// Miga de pan "Ruta › Módulo › Tema".
  final String? migaDePan;

  /// Recompensa anunciada.
  final RecompensaSimple? vistaPreviaRecompensa;

  /// Duración estimada.
  final int segundosEstimados;

  /// Minutos estimados, redondeados hacia arriba.
  int get minutosEstimados =>
      segundosEstimados <= 0 ? 0 : (segundosEstimados / 60).ceil();

  /// ¿Hay algo concreto que continuar?
  bool get hayAlgoQueHacer => tipo != TipoAccionContinuar.ninguna;
}

/// Aviso del panel sobre una generación en curso (`generation_banner`).
class BannerGeneracion {
  const BannerGeneracion({
    this.rutaId,
    this.titulo,
    this.estado = EstadoTrabajo.ejecutando,
    this.porcentaje = 0,
    this.mensaje,
    this.primerModuloListo = false,
  });

  /// Lee el bloque `generation_banner`.
  factory BannerGeneracion.desdeJson(Map<String, dynamic> json) => BannerGeneracion(
        rutaId: _txtN(_alguna(json, <String>['path_id', 'learning_path_id'])),
        titulo: _txtN(_alguna(json, <String>['title', 'path_title'])),
        estado: EstadoTrabajo.desdeApi(json['status']),
        porcentaje: _dec(_alguna(json, <String>['progress_pct', 'progress'])),
        mensaje: _txtN(_alguna(json, <String>['message', 'stage', 'label'])),
        primerModuloListo: _bol(json['first_module_ready']),
      );

  /// Ruta que se está forjando.
  final String? rutaId;

  /// Título de la ruta.
  final String? titulo;

  /// Estado del trabajo.
  final EstadoTrabajo estado;

  /// Avance de 0 a 100.
  final double porcentaje;

  /// Etapa en palabras.
  final String? mensaje;

  /// ¿El módulo 1 ya se puede empezar?
  final bool primerModuloListo;

  /// Progreso entre 0 y 1.
  double get fraccion => (porcentaje / 100).clamp(0, 1).toDouble();

  /// ¿Sigue trabajando?
  bool get enMarcha =>
      estado == EstadoTrabajo.pendiente || estado == EstadoTrabajo.ejecutando;
}

/// Resumen semanal del panel (`week_stats`).
class EstadisticasSemana {
  const EstadisticasSemana({
    this.segundosActivos = 0,
    this.lecciones = 0,
    this.logros = 0,
  });

  /// Lee `{active_seconds, lessons, achievements}`.
  factory EstadisticasSemana.desdeJson(Map<String, dynamic> json) =>
      EstadisticasSemana(
        segundosActivos: _ent(_alguna(json, <String>['active_seconds', 'seconds'])),
        lecciones: _ent(json['lessons']),
        logros: _ent(json['achievements']),
      );

  /// Tiempo efectivo de la semana.
  final int segundosActivos;

  /// Lecciones completadas en la semana.
  final int lecciones;

  /// Logros desbloqueados en la semana.
  final int logros;

  /// Minutos de la semana.
  int get minutos => (segundosActivos / 60).round();
}

/// Un día de actividad para los gráficos de barras (P17 y P04).
class DiaActividad {
  const DiaActividad({
    required this.fecha,
    this.minutos = 0,
    this.segundosActivos = 0,
    this.xp = 0,
    this.lecciones = 0,
    this.actividades = 0,
    this.preguntas = 0,
    this.correctas = 0,
    this.objetivoCumplido = false,
  });

  /// Lee un elemento de `last_7_days[]` o de `daily[]`.
  factory DiaActividad.desdeJson(Map<String, dynamic> json) {
    final int segundos = _ent(_alguna(json, <String>['active_seconds', 'seconds']));
    return DiaActividad(
      fecha: fechaDia(_alguna(json, <String>['date', 'local_date'])) ?? DateTime(1970),
      minutos: _ent(json['minutes'], (segundos / 60).round()),
      segundosActivos: segundos,
      xp: _ent(_alguna(json, <String>['xp', 'educational_xp', 'xp_total'])),
      lecciones: _ent(_alguna(json, <String>['lessons', 'lessons_completed'])),
      actividades: _ent(_alguna(json, <String>['activities', 'activities_completed'])),
      preguntas: _ent(_alguna(json, <String>['questions', 'questions_total'])),
      correctas: _ent(_alguna(json, <String>['correct', 'questions_correct'])),
      objetivoCumplido: _bol(json['goal_met']),
    );
  }

  /// Día local.
  final DateTime fecha;

  /// Minutos de estudio.
  final int minutos;

  /// Tiempo efectivo en segundos.
  final int segundosActivos;

  /// XP del día.
  final int xp;

  /// Lecciones completadas.
  final int lecciones;

  /// Actividades completadas.
  final int actividades;

  /// Preguntas respondidas.
  final int preguntas;

  /// Aciertos.
  final int correctas;

  /// ¿Se cumplió el objetivo diario?
  final bool objetivoCumplido;

  /// ¿Hubo actividad ese día?
  bool get tuvoActividad => minutos > 0 || xp > 0 || actividades > 0;
}

/// Las seis estadísticas héroe del perfil (`ProfileOut.stats`).
class EstadisticasPerfil {
  const EstadisticasPerfil({
    this.xpTotal = 0,
    this.rachaActual = 0,
    this.segundosEstudio = 0,
    this.areasDominadas = 0,
    this.logrosDesbloqueados = 0,
    this.itemsPoseidos = 0,
    this.temasDominados = 0,
    this.leccionesCompletadas = 0,
  });

  /// Lee `{xp_total, streak_current, study_seconds, areas_mastered, …}`.
  factory EstadisticasPerfil.desdeJson(Map<String, dynamic> json) =>
      EstadisticasPerfil(
        xpTotal: _ent(json['xp_total']),
        rachaActual: _ent(_alguna(json, <String>['streak_current', 'streak'])),
        segundosEstudio:
            _ent(_alguna(json, <String>['study_seconds', 'active_seconds'])),
        areasDominadas: _ent(json['areas_mastered']),
        logrosDesbloqueados: _ent(json['achievements_unlocked']),
        itemsPoseidos: _ent(json['items_owned']),
        temasDominados: _ent(json['topics_mastered']),
        leccionesCompletadas: _ent(json['lessons_completed']),
      );

  /// XP total acumulado.
  final int xpTotal;

  /// Racha actual en días.
  final int rachaActual;

  /// Tiempo total de estudio en segundos.
  final int segundosEstudio;

  /// Conocimientos dominados.
  final int areasDominadas;

  /// Logros desbloqueados.
  final int logrosDesbloqueados;

  /// Ítems poseídos.
  final int itemsPoseidos;

  /// Temas dominados.
  final int temasDominados;

  /// Lecciones completadas.
  final int leccionesCompletadas;

  /// Horas de estudio, redondeadas hacia abajo.
  int get horasEstudio => segundosEstudio ~/ 3600;

  /// Minutos sueltos además de las horas.
  int get minutosSueltos => (segundosEstudio % 3600) ~/ 60;

  /// Tiempo legible ("3h 10m").
  String get tiempoLegible {
    if (segundosEstudio < 60) return '0m';
    if (horasEstudio == 0) return '${minutosSueltos}m';
    return '${horasEstudio}h ${minutosSueltos}m';
  }

  /// ¿El usuario aún no tiene nada que mostrar?
  bool get estaVacio =>
      xpTotal == 0 && segundosEstudio == 0 && logrosDesbloqueados == 0;
}

/// Perfil de videojuego del usuario (`ProfileOut`).
class Perfil {
  const Perfil({
    this.personaje,
    this.capasAvatar = const <CapaAvatar>[],
    this.estadisticas = const EstadisticasPerfil(),
    this.conocimientos = const <AreaConocimiento>[],
    this.ultimos7Dias = const <DiaActividad>[],
    this.logrosRecientes = const <Logro>[],
  });

  /// Lee `{character, avatar_layers, stats, knowledge[], last_7_days[]}`.
  factory Perfil.desdeJson(Map<String, dynamic> json) {
    final List<CapaAvatar> capas = _lista(json['avatar_layers'], CapaAvatar.desdeJson)
      ..sort((CapaAvatar a, CapaAvatar b) => a.z.compareTo(b.z));
    return Perfil(
      personaje: json['character'] is Map
          ? Personaje.desdeJson(_mapa(json['character']))
          : null,
      capasAvatar: List<CapaAvatar>.unmodifiable(capas),
      estadisticas: EstadisticasPerfil.desdeJson(_mapa(json['stats'])),
      conocimientos: _lista(json['knowledge'], AreaConocimiento.desdeJson),
      ultimos7Dias: _lista(
        _alguna(json, <String>['last_7_days', 'last_seven_days']),
        DiaActividad.desdeJson,
      ),
      logrosRecientes: _lista(
        _alguna(json, <String>['recent_achievements', 'achievements']),
        Logro.desdeJson,
      ),
    );
  }

  /// Personaje con nivel, XP y rango.
  final Personaje? personaje;

  /// Manifiesto de capas ya ordenado por z.
  final List<CapaAvatar> capasAvatar;

  /// Las seis estadísticas héroe.
  final EstadisticasPerfil estadisticas;

  /// Conocimientos con nivel, XP, dominio y tiempo.
  final List<AreaConocimiento> conocimientos;

  /// Minutos por día de la última semana.
  final List<DiaActividad> ultimos7Dias;

  /// Logros recientes, si el servidor los adjunta.
  final List<Logro> logrosRecientes;

  /// Minutos del día con más estudio, para escalar el gráfico.
  int get maximoMinutos {
    int maximo = 0;
    for (final DiaActividad d in ultimos7Dias) {
      if (d.minutos > maximo) maximo = d.minutos;
    }
    return maximo;
  }
}

/// Totales acumulados del rango consultado (`StatsOut.totals`).
class TotalesEstadisticas {
  const TotalesEstadisticas({
    this.segundosActivos = 0,
    this.xp = 0,
    this.oro = 0,
    this.lecciones = 0,
    this.actividades = 0,
    this.preguntas = 0,
    this.correctas = 0,
    this.diasActivos = 0,
  });

  /// Lee el bloque `totals`, tolerando nombres alternativos.
  factory TotalesEstadisticas.desdeJson(Map<String, dynamic> json) =>
      TotalesEstadisticas(
        segundosActivos:
            _ent(_alguna(json, <String>['active_seconds', 'study_seconds'])),
        xp: _ent(_alguna(json, <String>['xp', 'xp_total', 'educational_xp'])),
        oro: _ent(_alguna(json, <String>['gold', 'gold_total'])),
        lecciones: _ent(_alguna(json, <String>['lessons', 'lessons_completed'])),
        actividades:
            _ent(_alguna(json, <String>['activities', 'activities_completed'])),
        preguntas: _ent(_alguna(json, <String>['questions', 'questions_total'])),
        correctas: _ent(_alguna(json, <String>['correct', 'questions_correct'])),
        diasActivos: _ent(_alguna(json, <String>['active_days', 'days'])),
      );

  /// Tiempo efectivo total.
  final int segundosActivos;

  /// XP del periodo.
  final int xp;

  /// Oro del periodo.
  final int oro;

  /// Lecciones completadas.
  final int lecciones;

  /// Actividades completadas.
  final int actividades;

  /// Preguntas respondidas.
  final int preguntas;

  /// Aciertos.
  final int correctas;

  /// Días activos del periodo.
  final int diasActivos;

  /// Minutos del periodo.
  int get minutos => (segundosActivos / 60).round();
}

/// Estadísticas ampliadas con rango de fechas (`StatsOut`).
class Estadisticas {
  const Estadisticas({
    this.diario = const <DiaActividad>[],
    this.totales = const TotalesEstadisticas(),
    this.precision = 0,
    this.lecciones = 0,
    this.evaluaciones = 0,
    this.desde,
    this.hasta,
  });

  /// Lee `{daily[], totals, accuracy_pct, lessons, assessments}`.
  factory Estadisticas.desdeJson(Map<String, dynamic> json) => Estadisticas(
        diario: _lista(_alguna(json, <String>['daily', 'days']), DiaActividad.desdeJson),
        totales: TotalesEstadisticas.desdeJson(_mapa(json['totals'])),
        precision: _dec(_alguna(json, <String>['accuracy_pct', 'accuracy'])),
        lecciones: _ent(json['lessons']),
        evaluaciones: _ent(json['assessments']),
        desde: fechaDia(json['from']),
        hasta: fechaDia(json['to']),
      );

  /// Serie diaria del rango.
  final List<DiaActividad> diario;

  /// Totales del rango.
  final TotalesEstadisticas totales;

  /// Precisión global en porcentaje.
  final double precision;

  /// Lecciones completadas en el rango.
  final int lecciones;

  /// Evaluaciones rendidas en el rango.
  final int evaluaciones;

  /// Primer día del rango.
  final DateTime? desde;

  /// Último día del rango.
  final DateTime? hasta;

  /// ¿No hay nada que graficar?
  bool get estaVacio =>
      diario.isEmpty || diario.every((DiaActividad d) => !d.tuvoActividad);
}

/// Todo lo que el panel principal (P04) necesita en una sola llamada.
class Panel {
  const Panel({
    this.claveSaludo = '',
    this.personaje,
    this.saldoOro = 0,
    this.racha = const Racha(),
    this.objetivoDiario = const ObjetivoDiario(),
    this.accionContinuar = const AccionContinuar(),
    this.conocimientos = const <AreaConocimiento>[],
    this.misiones = const <Mision>[],
    this.estadisticasSemana = const EstadisticasSemana(),
    this.bannerGeneracion,
    this.notificacionesSinLeer = 0,
    this.capasAvatar = const <CapaAvatar>[],
  });

  /// Lee `DashboardOut` completo.
  factory Panel.desdeJson(Map<String, dynamic> json) {
    final List<CapaAvatar> capas = _lista(json['avatar_layers'], CapaAvatar.desdeJson)
      ..sort((CapaAvatar a, CapaAvatar b) => a.z.compareTo(b.z));
    final Map<String, dynamic>? banner = _mapaN(json['generation_banner']);
    return Panel(
      claveSaludo: _txt(json['greeting_key']),
      personaje: json['character'] is Map
          ? Personaje.desdeJson(_mapa(json['character']))
          : null,
      saldoOro: _ent(_alguna(json, <String>['gold_balance', 'gold'])),
      racha: Racha.desdeJson(_mapa(json['streak'])),
      objetivoDiario: ObjetivoDiario.desdeJson(_mapa(json['daily_goal'])),
      accionContinuar: AccionContinuar.desdeJson(_mapa(json['continue_action'])),
      conocimientos: _lista(json['knowledge_summary'], AreaConocimiento.desdeJson),
      misiones: _lista(json['missions_summary'], Mision.desdeJson),
      estadisticasSemana: EstadisticasSemana.desdeJson(_mapa(json['week_stats'])),
      bannerGeneracion:
          banner == null || banner.isEmpty ? null : BannerGeneracion.desdeJson(banner),
      notificacionesSinLeer: _ent(
        _alguna(json, <String>['unread_notifications', 'notifications_unread']),
      ),
      capasAvatar: List<CapaAvatar>.unmodifiable(capas),
    );
  }

  /// Clave del saludo que el servidor elige según la hora y el estado.
  final String claveSaludo;

  /// Personaje con nivel, rango y progreso de XP.
  final Personaje? personaje;

  /// Saldo de oro vigente.
  final int saldoOro;

  /// Estado de la racha.
  final Racha racha;

  /// Objetivo diario y su progreso de hoy.
  final ObjetivoDiario objetivoDiario;

  /// Qué propone el botón "Continuar".
  final AccionContinuar accionContinuar;

  /// Conocimientos activos con su dominio.
  final List<AreaConocimiento> conocimientos;

  /// Misiones del día, resumidas.
  final List<Mision> misiones;

  /// Resumen de la semana.
  final EstadisticasSemana estadisticasSemana;

  /// Aviso de generación en curso, si lo hay.
  final BannerGeneracion? bannerGeneracion;

  /// Notificaciones sin leer para la campana.
  final int notificacionesSinLeer;

  /// Capas del avatar para el encabezado.
  final List<CapaAvatar> capasAvatar;

  /// ¿El usuario todavía no tiene ninguna Ruta?
  bool get sinRutas =>
      accionContinuar.tipo == TipoAccionContinuar.crearRuta && conocimientos.isEmpty;
}

// ---------------------------------------------------------------------------
// §7.4 (bis) Perfil de conocimiento del usuario
// ---------------------------------------------------------------------------

/// Fila del perfil de conocimiento del usuario (`UserKnowledgeOut`).
class ConocimientoUsuario {
  const ConocimientoUsuario({
    required this.area,
    this.temasDominados = 0,
    this.temasTotales = 0,
    this.modulosCompletados = 0,
    this.rutasActivas = 0,
    this.primeraActividadEn,
    this.decaimientoAplicado = 0,
  });

  /// Lee `UserKnowledgeOut`: el área más los contadores de progreso.
  factory ConocimientoUsuario.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> area = json['knowledge_area'] is Map
        ? _mapa(json['knowledge_area'])
        : (json['area'] is Map ? _mapa(json['area']) : json);
    return ConocimientoUsuario(
      area: AreaConocimiento.desdeJson(<String, dynamic>{...area, ...json}),
      temasDominados: _ent(json['topics_mastered']),
      temasTotales: _ent(json['topics_total']),
      modulosCompletados: _ent(json['modules_completed']),
      rutasActivas: _ent(_alguna(json, <String>['active_paths', 'paths_active'])),
      primeraActividadEn: fechaHora(json['first_activity_at']),
      decaimientoAplicado: _dec(json['decay_applied']),
    );
  }

  /// Conocimiento con su nivel, XP, dominio y tiempo.
  final AreaConocimiento area;

  /// Temas dominados dentro del conocimiento.
  final int temasDominados;

  /// Temas totales conocidos.
  final int temasTotales;

  /// Módulos completados.
  final int modulosCompletados;

  /// Rutas activas que aportan a este conocimiento.
  final int rutasActivas;

  /// Primera vez que estudió este conocimiento.
  final DateTime? primeraActividadEn;

  /// Decaimiento aplicado por el servidor (curva de olvido).
  final double decaimientoAplicado;

  /// Identificador del conocimiento.
  String get id => area.id;

  /// Identificador estable en texto (`sql`).
  String get slug => area.slug;

  /// Nombre visible.
  String get nombre => area.nombre;

  /// Nombre corto para chips y medallones.
  String get nombreCorto => area.nombreCorto;

  /// Categoría del conocimiento.
  CategoriaConocimiento get categoria => area.categoria;

  /// Descripción del conocimiento.
  String? get descripcion => area.descripcion;

  /// Icono del conocimiento.
  String? get iconoKey => area.iconoKey;

  /// Color de acento propuesto por el servidor.
  String? get colorAcento => area.colorAcento;

  /// Nivel del usuario dentro del conocimiento.
  int get nivel => area.nivel;

  /// XP acumulado en el conocimiento.
  int get xp => area.xp;

  /// Título de rango del conocimiento ("Competente en").
  String? get tituloRango => area.tituloRango;

  /// Dominio actual (0–100), calculado por el servidor.
  double get dominio => area.dominio;

  /// Tiempo de estudio acumulado en segundos.
  int get segundosEstudio => area.segundosEstudio;

  /// Estado de dominio.
  EstadoDominio get estado => area.estado;

  /// Última vez que estudió este conocimiento.
  DateTime? get ultimaActividadEn => area.ultimaActividadEn;

  /// ¿Hay algo que mostrar en la ficha?
  bool get tieneProgreso => area.tieneProgreso;
}

// ---------------------------------------------------------------------------
// §7.9 Misiones, logros y notificaciones
// ---------------------------------------------------------------------------

/// Misión asignada al usuario (`user_missions`).
class Mision {
  const Mision({
    required this.id,
    this.codigoPlantilla = '',
    this.ambito = AmbitoMision.diaria,
    this.nivel,
    this.titulo = '',
    this.descripcion,
    this.meta = 1,
    this.progreso = 0,
    this.estado = EstadoMision.activa,
    this.recompensaXp = 0,
    this.recompensaOro = 0,
    this.itemRecompensa,
    this.rutaId,
    this.areaConocimientoId,
    this.expiraEn,
    this.completadaEn,
    this.reclamadaEn,
    this.accionSugerida,
    this.enlaceProfundo,
  });

  /// Lee `MissionOut` y el resumen de misiones del panel.
  factory Mision.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> recompensa = _mapa(json['reward']);
    return Mision(
      id: _txt(_alguna(json, <String>['user_mission_id', 'id'])),
      codigoPlantilla: _txt(_alguna(json, <String>['template_code', 'code'])),
      ambito: AmbitoMision.desdeApi(json['scope']),
      nivel: desdeClaveApiOpcional(NivelMision.values, json['tier']),
      titulo: _txt(json['title']),
      descripcion: _txtN(_alguna(json, <String>['description', 'narrative'])),
      meta: _ent(json['target'], 1),
      progreso: _ent(json['progress']),
      estado: EstadoMision.desdeApi(json['status']),
      recompensaXp: _ent(
        _alguna(json, <String>['reward_xp', 'xp']) ?? recompensa['xp'],
      ),
      recompensaOro: _ent(
        _alguna(json, <String>['reward_gold', 'gold']) ?? recompensa['gold'],
      ),
      itemRecompensa:
          json['reward_item'] is Map ? Item.desdeJson(_mapa(json['reward_item'])) : null,
      rutaId: _txtN(_alguna(json, <String>['learning_path_id', 'path_id'])),
      areaConocimientoId: _txtN(json['knowledge_area_id']),
      expiraEn: fechaHora(json['expires_at']),
      completadaEn: fechaHora(json['completed_at']),
      reclamadaEn: fechaHora(json['claimed_at']),
      accionSugerida: _txtN(_alguna(json, <String>['suggested_action', 'cta_label'])),
      enlaceProfundo: _txtN(_alguna(json, <String>['deep_link', 'cta_link'])),
    );
  }

  /// Identificador de la instancia (`user_mission_id`).
  final String id;

  /// Código de la plantilla (`D01`, `S02`…).
  final String codigoPlantilla;

  /// Diaria, semanal o de ruta.
  final AmbitoMision ambito;

  /// Dificultad de la instancia.
  final NivelMision? nivel;

  /// Título ya interpolado ("Completa 2 lecciones").
  final String titulo;

  /// Texto narrativo de apoyo.
  final String? descripcion;

  /// Objetivo numérico.
  final int meta;

  /// Avance actual.
  final int progreso;

  /// Estado de la misión.
  final EstadoMision estado;

  /// XP que otorga, calculado por el servidor.
  final int recompensaXp;

  /// Oro que otorga.
  final int recompensaOro;

  /// Ítem que entrega, si lo hay.
  final Item? itemRecompensa;

  /// Ruta a la que apunta.
  final String? rutaId;

  /// Conocimiento al que apunta.
  final String? areaConocimientoId;

  /// Medianoche local en que expira.
  final DateTime? expiraEn;

  /// Cuándo se cumplió.
  final DateTime? completadaEn;

  /// Cuándo se reclamó la recompensa.
  final DateTime? reclamadaEn;

  /// Sugerencia concreta ("Completa 1 lección: Filtros L3").
  final String? accionSugerida;

  /// Enlace profundo de la sugerencia.
  final String? enlaceProfundo;

  /// Progreso entre 0 y 1.
  double get fraccion => meta <= 0 ? 0 : (progreso / meta).clamp(0, 1).toDouble();

  /// ¿Ya está cumplida?
  bool get estaCumplida =>
      estado == EstadoMision.completada || estado == EstadoMision.reclamada;

  /// ¿Se puede pulsar "Reclamar"?
  bool get sePuedeReclamar => estado.sePuedeReclamar;

  /// Resumen de la recompensa ("+100 XP · +30 Oro").
  String get recompensaLegible => RecompensaSimple(
        xp: recompensaXp,
        oro: recompensaOro,
        nombreItem: itemRecompensa?.nombre,
      ).resumen;
}

/// Misiones del día agrupadas por horizonte (`MissionsOut`).
class Misiones {
  const Misiones({
    this.diarias = const <Mision>[],
    this.semanales = const <Mision>[],
    this.especiales = const <Mision>[],
    this.segundosParaReinicio = 0,
  });

  /// Lee `{daily[], special[], weekly[], resets_in_seconds}`.
  factory Misiones.desdeJson(Map<String, dynamic> json) => Misiones(
        diarias: _lista(json['daily'], Mision.desdeJson),
        semanales: _lista(json['weekly'], Mision.desdeJson),
        especiales: _lista(json['special'], Mision.desdeJson),
        segundosParaReinicio: _ent(
          _alguna(json, <String>['resets_in_seconds', 'reset_in_seconds']),
        ),
      );

  /// Misiones diarias.
  final List<Mision> diarias;

  /// Misiones semanales (fase 2, normalmente vacías).
  final List<Mision> semanales;

  /// Misiones de ruta.
  final List<Mision> especiales;

  /// Segundos que faltan para el reinicio de medianoche local.
  final int segundosParaReinicio;

  /// Misiones de un grupo concreto.
  List<Mision> porAmbito(AmbitoMision ambito) => switch (ambito) {
        AmbitoMision.diaria => diarias,
        AmbitoMision.semanal => semanales,
        AmbitoMision.especial => especiales,
      };

  /// ¿Están todas las diarias cumplidas?
  bool get todasCumplidas =>
      diarias.isNotEmpty && diarias.every((Mision m) => m.estaCumplida);

  /// ¿No hay ninguna misión que mostrar?
  bool get estaVacio =>
      diarias.isEmpty && semanales.isEmpty && especiales.isEmpty;
}

/// Un nivel de un logro con su objetivo y recompensa (`achievements.tiers`).
class NivelDeLogro {
  const NivelDeLogro({
    this.nivel = NivelLogro.bronce,
    this.objetivo = 0,
    this.recompensa = const RecompensaSimple(),
    this.desbloqueadoEn,
  });

  /// Lee `{tier, target, reward:{xp, gold, title_id}}`.
  factory NivelDeLogro.desdeJson(Map<String, dynamic> json) => NivelDeLogro(
        nivel: NivelLogro.desdeApi(json['tier']),
        objetivo: _ent(json['target']),
        recompensa:
            RecompensaSimple.desdeCampo(json['reward']) ?? const RecompensaSimple(),
        desbloqueadoEn: fechaHora(json['unlocked_at']),
      );

  /// Bronce, plata, oro o único.
  final NivelLogro nivel;

  /// Cuánto hay que acumular para alcanzarlo.
  final int objetivo;

  /// Qué entrega.
  final RecompensaSimple recompensa;

  /// Cuándo se desbloqueó, si ya ocurrió.
  final DateTime? desbloqueadoEn;

  /// ¿Ya está conseguido?
  bool get estaDesbloqueado => desbloqueadoEn != null;
}

/// Logro de la sala de trofeos (`AchievementOut`).
class Logro {
  const Logro({
    this.codigo = '',
    this.id,
    this.nombre = '',
    this.descripcion,
    this.categoria = CategoriaLogro.aprendizaje,
    this.visibilidad = VisibilidadLogro.visible,
    this.nivelMasAlto,
    this.niveles = const <NivelDeLogro>[],
    this.porcentajeProgreso = 0,
    this.progresoActual = 0,
    this.objetivoActual = 0,
    this.desbloqueadoEn,
    this.iconoKey,
    this.orden = 100,
  });

  /// Lee `AchievementOut`.
  factory Logro.desdeJson(Map<String, dynamic> json) => Logro(
        codigo: _txt(json['code']),
        id: _txtN(json['id']),
        nombre: _txt(json['name']),
        descripcion: _txtN(_alguna(json, <String>['description', 'hint'])),
        categoria: CategoriaLogro.desdeApi(json['category']),
        visibilidad: VisibilidadLogro.desdeApi(json['visibility']),
        nivelMasAlto: desdeClaveApiOpcional(NivelLogro.values, json['highest_tier']),
        niveles: _lista(json['tiers'], NivelDeLogro.desdeJson),
        porcentajeProgreso: _dec(json['progress_pct']),
        progresoActual: _ent(_alguna(json, <String>['progress', 'counter'])),
        objetivoActual: _ent(_alguna(json, <String>['target', 'next_target'])),
        desbloqueadoEn: fechaHora(
          _alguna(json, <String>['unlocked_at', 'last_unlocked_at']),
        ),
        iconoKey: _txtN(json['icon_key']),
        orden: _ent(json['sort_order'], 100),
      );

  /// Código estable (`ACH_ORACLE`).
  final String codigo;

  /// Identificador, cuando el servidor lo envía.
  final String? id;

  /// Nombre visible ("Oráculo").
  final String nombre;

  /// Descripción o pista si es secreto.
  final String? descripcion;

  /// Pestaña de la sala de trofeos.
  final CategoriaLogro categoria;

  /// Visible o secreto.
  final VisibilidadLogro visibilidad;

  /// Nivel más alto ya desbloqueado.
  final NivelLogro? nivelMasAlto;

  /// Niveles definidos, en orden ascendente.
  final List<NivelDeLogro> niveles;

  /// Avance hacia el próximo nivel, en porcentaje.
  final double porcentajeProgreso;

  /// Avance absoluto ("62" de "62/100").
  final int progresoActual;

  /// Objetivo del próximo nivel ("100" de "62/100").
  final int objetivoActual;

  /// Cuándo se desbloqueó el último nivel.
  final DateTime? desbloqueadoEn;

  /// Medalla que lo representa.
  final String? iconoKey;

  /// Orden dentro de la cuadrícula.
  final int orden;

  /// ¿Tiene al menos un nivel desbloqueado?
  bool get estaDesbloqueado => nivelMasAlto != null || desbloqueadoEn != null;

  /// ¿Se muestra como silueta con pista?
  bool get esSecreto =>
      visibilidad == VisibilidadLogro.oculto && !estaDesbloqueado;

  /// Progreso entre 0 y 1.
  double get fraccion {
    if (objetivoActual > 0) {
      return (progresoActual / objetivoActual).clamp(0, 1).toDouble();
    }
    return (porcentajeProgreso / 100).clamp(0, 1).toDouble();
  }

  /// ¿Está a punto de conseguirse? ("casi lo tienes" ≥ 80 %).
  bool get estaCerca => !estaDesbloqueado && fraccion >= 0.8;

  /// Texto de progreso ("62/100"), vacío si no es acumulativo.
  String get progresoLegible =>
      objetivoActual > 0 ? '$progresoActual/$objetivoActual' : '';
}

/// Notificación de la bandeja in-app (`NotificationOut`).
class Notificacion {
  const Notificacion({
    required this.id,
    this.tipo = TipoNotificacion.sistema,
    this.estado = EstadoNotificacion.pendiente,
    this.titulo = '',
    this.cuerpo = '',
    this.enlaceProfundo,
    this.carga = const <String, dynamic>{},
    this.programadaPara,
    this.enviadaEn,
    this.leidaEn,
    this.descartadaEn,
  });

  /// Lee `NotificationOut`.
  factory Notificacion.desdeJson(Map<String, dynamic> json) => Notificacion(
        id: _txt(_alguna(json, <String>['id', 'notification_id'])),
        tipo: TipoNotificacion.desdeApi(
          _alguna(json, <String>['notification_type', 'type']),
        ),
        estado: EstadoNotificacion.desdeApi(json['status']),
        titulo: _txt(json['title']),
        cuerpo: _txt(_alguna(json, <String>['body', 'message'])),
        enlaceProfundo: _txtN(json['deep_link']),
        carga: _mapa(json['payload']),
        programadaPara: fechaHora(json['scheduled_for']),
        enviadaEn: fechaHora(json['sent_at']),
        leidaEn: fechaHora(json['read_at']),
        descartadaEn: fechaHora(json['dismissed_at']),
      );

  /// Identificador de la notificación.
  final String id;

  /// Tipo, que decide el icono.
  final TipoNotificacion tipo;

  /// Estado de entrega o lectura.
  final EstadoNotificacion estado;

  /// Título en español, con tono de recuperación.
  final String titulo;

  /// Cuerpo del mensaje.
  final String cuerpo;

  /// Destino al tocarla (`home`, `streak`, `missions`, `route/{id}`).
  final String? enlaceProfundo;

  /// Datos extra para el cliente.
  final Map<String, dynamic> carga;

  /// Envío programado.
  final DateTime? programadaPara;

  /// Envío efectivo.
  final DateTime? enviadaEn;

  /// Cuándo se leyó.
  final DateTime? leidaEn;

  /// Cuándo se descartó.
  final DateTime? descartadaEn;

  /// ¿Ya la leyó el usuario?
  bool get estaLeida => leidaEn != null || estado == EstadoNotificacion.leida;

  /// Momento que se muestra en la lista.
  DateTime? get fechaVisible => enviadaEn ?? programadaPara ?? leidaEn;
}

/// Una fila de la tabla de niveles (`level_definitions`).
class DefinicionNivel {
  const DefinicionNivel({
    this.nivel = 1,
    this.xpRequerido = 0,
    this.xpDelta = 0,
    this.tituloRango = '',
    this.esInicioDeRango = false,
    this.desbloqueos = const <String, dynamic>{},
  });

  /// Lee `{level, xp_required, xp_delta, rank_title, is_rank_start, unlocks}`.
  factory DefinicionNivel.desdeJson(Map<String, dynamic> json) => DefinicionNivel(
        nivel: _ent(json['level'], 1),
        xpRequerido: _ent(json['xp_required']),
        xpDelta: _ent(json['xp_delta']),
        tituloRango: _txt(json['rank_title']),
        esInicioDeRango: _bol(json['is_rank_start']),
        desbloqueos: _mapa(json['unlocks']),
      );

  /// Nivel 1..50.
  final int nivel;

  /// XP acumulado necesario para alcanzarlo.
  final int xpRequerido;

  /// XP entre este nivel y el anterior.
  final int xpDelta;

  /// Título del rango vigente en ese nivel.
  final String tituloRango;

  /// ¿Empieza un rango nuevo?
  final bool esInicioDeRango;

  /// Qué habilita (`shop_rarities`, `gold_bonus`).
  final Map<String, dynamic> desbloqueos;

  /// Rarezas que habilita en el Mercado.
  List<String> get rarezasTienda => _textos(desbloqueos['shop_rarities']);

  /// Oro de bonificación al alcanzarlo.
  int get oroBonus => _ent(desbloqueos['gold_bonus']);
}

/// Claves públicas de `game_configs` más las curvas de nivel.
class ConfigPublica {
  const ConfigPublica({
    this.versionConfig = 0,
    this.valores = const <String, dynamic>{},
    this.niveles = const <DefinicionNivel>[],
    this.nivelesConocimiento = const <DefinicionNivel>[],
  });

  /// Lee `{config_version, values{}, levels[], knowledge_levels[]}`.
  factory ConfigPublica.desdeJson(Map<String, dynamic> json) => ConfigPublica(
        versionConfig: _ent(json['config_version']),
        valores: _mapa(json['values']),
        niveles: _lista(json['levels'], DefinicionNivel.desdeJson),
        nivelesConocimiento:
            _lista(json['knowledge_levels'], DefinicionNivel.desdeJson),
      );

  /// Versión vigente de la configuración de juego.
  final int versionConfig;

  /// Claves públicas con su valor tal cual.
  final Map<String, dynamic> valores;

  /// Curva de nivel global.
  final List<DefinicionNivel> niveles;

  /// Curva de nivel por conocimiento.
  final List<DefinicionNivel> nivelesConocimiento;

  /// Valor entero de una clave (`xp.lesson_completed`).
  int entero(String clave, [int porDefecto = 0]) =>
      _ent(valores[clave], porDefecto);

  /// Valor decimal de una clave.
  double decimal(String clave, [double porDefecto = 0]) =>
      _dec(valores[clave], porDefecto);

  /// Valor booleano de una clave.
  bool booleano(String clave, [bool porDefecto = false]) =>
      _bol(valores[clave], porDefecto);

  /// Valor textual de una clave.
  String texto(String clave, [String porDefecto = '']) =>
      _txt(valores[clave], porDefecto);

  /// Valor de mapa de una clave (`items.rarity_colors`).
  Map<String, dynamic> mapa(String clave) => _mapa(valores[clave]);

  /// Valor de lista de textos de una clave (`items.slots_active`).
  List<String> lista(String clave) => _textos(valores[clave]);

  /// Colores de rareza que publica el servidor.
  Map<String, String?> get coloresRareza => _mapaTextos(valores['items.rarity_colors']);

  /// Precio por rareza.
  Map<String, dynamic> get preciosPorRareza => mapa('shop.price_by_rarity');

  /// Definición de un nivel global concreto.
  DefinicionNivel? nivelGlobal(int nivel) {
    for (final DefinicionNivel d in niveles) {
      if (d.nivel == nivel) return d;
    }
    return null;
  }
}

/// Salud del servicio (`GET /health`).
class Salud {
  const Salud({this.estado = '', this.baseDatos = '', this.version = ''});

  /// Lee `{"status": "ok", "database": "ok", "version": "1.0.0"}`.
  factory Salud.desdeJson(Map<String, dynamic> json) => Salud(
        estado: _txt(json['status']),
        baseDatos: _txt(json['database']),
        version: _txt(json['version']),
      );

  /// Estado del servicio.
  final String estado;

  /// Estado de la base de datos.
  final String baseDatos;

  /// Versión desplegada.
  final String version;

  /// ¿Todo en orden?
  bool get estaBien => estado == 'ok' && baseDatos == 'ok';
}

// ---------------------------------------------------------------------------
// §7.10 `RewardsReceipt` — objeto canónico de recompensas
//
// Es lo **único** que el cliente usa para animar. La app nunca calcula XP,
// oro, nivel ni dominio: todos los importes de abajo ya vienen aplicados.
// ---------------------------------------------------------------------------

/// Desglose de la XP otorgada (`receipt.xp`).
class XpRecibo {
  const XpRecibo({
    this.cantidad = 0,
    this.base = 0,
    this.xpActividad = 0,
    this.xpPreguntas = 0,
    this.multiplicador = 1,
    this.codigoMotivo,
    this.esEducativo = true,
    this.totalDespues = 0,
  });

  /// Lee `{amount, base_amount, activity_xp, question_xp, multiplier, …}`.
  factory XpRecibo.desdeJson(Map<String, dynamic> json) => XpRecibo(
        cantidad: _ent(json['amount']),
        base: _ent(json['base_amount']),
        xpActividad: _ent(json['activity_xp']),
        xpPreguntas: _ent(json['question_xp']),
        multiplicador: _dec(json['multiplier'], 1),
        codigoMotivo: _txtN(json['reason_code']),
        esEducativo: _bol(json['is_educational'], true),
        totalDespues: _ent(json['total_after']),
      );

  /// XP total otorgado por la acción.
  final int cantidad;

  /// XP base antes de multiplicadores.
  final int base;

  /// Parte que corresponde a completar la actividad.
  final int xpActividad;

  /// Parte que corresponde a las respuestas.
  final int xpPreguntas;

  /// Multiplicador aplicado (repetición, dificultad, tope diario).
  final double multiplicador;

  /// Código del motivo (`first_completion`, `repeat`…).
  final String? codigoMotivo;

  /// XP educativo o de bonificación.
  final bool esEducativo;

  /// XP total del usuario ya persistido.
  final int totalDespues;

  /// ¿Hay algo que animar?
  bool get hayAlgo => cantidad != 0;

  /// Motivo en español, con respaldo genérico si el código es desconocido.
  String get motivoLegible => switch (codigoMotivo) {
        'first_completion' => 'Primera vez',
        'repeat' => 'Repetición',
        'repeat_reduced' => 'Repetición',
        'review' => 'Repaso',
        'challenge' => 'Desafío',
        'assessment' => 'Desafío del módulo',
        'daily_softcap_50' => 'Tope diario aplicado',
        'daily_softcap_10' => 'Tope diario aplicado',
        'first_activity_of_day' => 'Primera actividad del día',
        _ => '',
      };
}

/// Oro otorgado y saldo posterior (`receipt.gold`).
class OroRecibo {
  const OroRecibo({
    this.cantidad = 0,
    this.saldoDespues = 0,
    this.codigoMotivo,
  });

  /// Lee `{amount, balance_after, reason_code}`.
  factory OroRecibo.desdeJson(Map<String, dynamic> json) => OroRecibo(
        cantidad: _ent(json['amount']),
        saldoDespues: _ent(json['balance_after']),
        codigoMotivo: _txtN(json['reason_code']),
      );

  /// Oro otorgado.
  final int cantidad;

  /// Saldo ya persistido tras la operación.
  final int saldoDespues;

  /// Código del motivo.
  final String? codigoMotivo;

  /// ¿Hay algo que animar?
  bool get hayAlgo => cantidad != 0;
}

/// Cambio de nivel global (`receipt.level`).
class NivelRecibo {
  const NivelRecibo({
    this.antes = 0,
    this.despues = 0,
    this.subioNivel = false,
    this.tituloRangoAntes,
    this.tituloRangoDespues,
    this.cambioRango = false,
    this.xpParaSiguiente = 0,
    this.porcentajeProgreso = 0,
    this.oroBonus = 0,
    this.rarezasDesbloqueadas = const <String>[],
  });

  /// Lee `{before, after, leveled_up, rank_title_before, …}`.
  factory NivelRecibo.desdeJson(Map<String, dynamic> json) => NivelRecibo(
        antes: _ent(json['before']),
        despues: _ent(json['after']),
        subioNivel: _bol(json['leveled_up']),
        tituloRangoAntes: _txtN(json['rank_title_before']),
        tituloRangoDespues: _txtN(json['rank_title_after']),
        cambioRango: _bol(json['rank_changed']),
        xpParaSiguiente: _ent(json['xp_to_next']),
        porcentajeProgreso: _dec(json['progress_pct']),
        oroBonus: _ent(json['gold_bonus']),
        rarezasDesbloqueadas: _textos(json['unlocked_shop_rarities']),
      );

  /// Nivel antes de la acción.
  final int antes;

  /// Nivel después de la acción.
  final int despues;

  /// ¿Subió de nivel? Si es `false`, no hay animación de nivel.
  final bool subioNivel;

  /// Título de rango anterior.
  final String? tituloRangoAntes;

  /// Título de rango vigente.
  final String? tituloRangoDespues;

  /// ¿Cambió también el rango?
  final bool cambioRango;

  /// XP que falta para el siguiente nivel.
  final int xpParaSiguiente;

  /// Progreso dentro del nivel, en porcentaje.
  final double porcentajeProgreso;

  /// Oro de bonificación por subir.
  final int oroBonus;

  /// Rarezas del Mercado que habilita.
  final List<String> rarezasDesbloqueadas;

  /// Progreso entre 0 y 1.
  double get fraccion => (porcentajeProgreso / 100).clamp(0, 1).toDouble();
}

/// Efecto sobre un conocimiento concreto (`receipt.knowledge`).
class ConocimientoRecibo {
  const ConocimientoRecibo({
    this.areaConocimientoId = '',
    this.nombre = '',
    this.xpDespues = 0,
    this.nivelAntes = 0,
    this.nivelDespues = 0,
    this.tituloRangoDespues,
    this.dominioAntes = 0,
    this.dominioDespues = 0,
    this.estado = EstadoDominio.sinEvidencia,
  });

  /// Lee `{knowledge_area_id, name, xp_after, level_before, …}`.
  factory ConocimientoRecibo.desdeJson(Map<String, dynamic> json) =>
      ConocimientoRecibo(
        areaConocimientoId: _txt(json['knowledge_area_id']),
        nombre: _txt(json['name']),
        xpDespues: _ent(json['xp_after']),
        nivelAntes: _ent(json['level_before']),
        nivelDespues: _ent(json['level_after']),
        tituloRangoDespues: _txtN(json['rank_title_after']),
        dominioAntes: _dec(json['mastery_before']),
        dominioDespues: _dec(json['mastery_after']),
        estado: EstadoDominio.desdeApi(json['status']),
      );

  /// Conocimiento afectado.
  final String areaConocimientoId;

  /// Nombre visible ("SQL").
  final String nombre;

  /// XP del conocimiento ya persistido.
  final int xpDespues;

  /// Nivel anterior.
  final int nivelAntes;

  /// Nivel vigente.
  final int nivelDespues;

  /// Título de rango del conocimiento ("Competente en").
  final String? tituloRangoDespues;

  /// Dominio anterior (0–100).
  final double dominioAntes;

  /// Dominio vigente (0–100).
  final double dominioDespues;

  /// Estado de dominio resultante.
  final EstadoDominio estado;

  /// Variación de dominio, ya calculada por el servidor.
  double get delta => dominioDespues - dominioAntes;

  /// ¿Subió de nivel dentro del conocimiento?
  bool get subioNivel => nivelDespues > nivelAntes;
}

/// Variación de dominio de un tema, módulo o ruta (`receipt.mastery_deltas`).
class DeltaDominio {
  const DeltaDominio({
    this.ambito = AmbitoDominio.tema,
    this.id = '',
    this.nombre = '',
    this.antes = 0,
    this.despues = 0,
    this.estado = EstadoDominio.sinEvidencia,
  });

  /// Lee `{scope, id, name, before, after, status}`.
  factory DeltaDominio.desdeJson(Map<String, dynamic> json) => DeltaDominio(
        ambito: AmbitoDominio.desdeApi(json['scope']),
        id: _txt(json['id']),
        nombre: _txt(json['name']),
        antes: _dec(json['before']),
        despues: _dec(json['after']),
        estado: EstadoDominio.desdeApi(json['status']),
      );

  /// A qué se refiere el delta.
  final AmbitoDominio ambito;

  /// Identificador del tema, módulo o ruta.
  final String id;

  /// Nombre visible.
  final String nombre;

  /// Dominio anterior.
  final double antes;

  /// Dominio posterior.
  final double despues;

  /// Estado resultante.
  final EstadoDominio estado;

  /// Variación, ya calculada por el servidor.
  double get delta => despues - antes;

  /// ¿Subió?
  bool get mejoro => delta > 0;
}

/// Efecto sobre la racha (`receipt.streak`).
class RachaRecibo {
  const RachaRecibo({
    this.actual = 0,
    this.mejor = 0,
    this.cambio = CambioRacha.extendida,
    this.estadoDia = EstadoDia.activo,
    this.esPrimeraActividadDelDia = false,
    this.hito,
  });

  /// Lee `{current, best, change, day_status, is_first_activity_of_day, …}`.
  factory RachaRecibo.desdeJson(Map<String, dynamic> json) => RachaRecibo(
        actual: _ent(json['current']),
        mejor: _ent(json['best']),
        cambio: CambioRacha.desdeApi(json['change']),
        estadoDia: EstadoDia.desdeApi(json['day_status']),
        esPrimeraActividadDelDia: _bol(json['is_first_activity_of_day']),
        hito: json['milestone'] is Map
            ? HitoRacha.desdeJson(_mapa(json['milestone']))
            : null,
      );

  /// Días consecutivos tras la acción.
  final int actual;

  /// Mejor racha histórica.
  final int mejor;

  /// Qué le pasó a la racha.
  final CambioRacha cambio;

  /// Estado del día de hoy.
  final EstadoDia estadoDia;

  /// Solo si es `true` se muestra el overlay de racha (§7.10 regla 2).
  final bool esPrimeraActividadDelDia;

  /// Hito alcanzado con esta acción, si lo hubo.
  final HitoRacha? hito;

  /// ¿Se alcanzó un hito?
  bool get alcanzoHito => hito != null;
}

/// Misión afectada por la acción (`receipt.missions`).
class MisionRecibo {
  const MisionRecibo({
    this.id = '',
    this.codigoPlantilla = '',
    this.titulo = '',
    this.progreso = 0,
    this.meta = 0,
    this.estado = EstadoMision.activa,
    this.reclamadaAuto = false,
    this.recompensa = const RecompensaSimple(),
  });

  /// Lee `{user_mission_id, template_code, title, progress, target, …}`.
  factory MisionRecibo.desdeJson(Map<String, dynamic> json) => MisionRecibo(
        id: _txt(_alguna(json, <String>['user_mission_id', 'id'])),
        codigoPlantilla: _txt(json['template_code']),
        titulo: _txt(json['title']),
        progreso: _ent(json['progress']),
        meta: _ent(json['target']),
        estado: EstadoMision.desdeApi(json['status']),
        reclamadaAuto: _bol(json['auto_claimed']),
        recompensa:
            RecompensaSimple.desdeCampo(json['reward']) ?? const RecompensaSimple(),
      );

  /// Instancia de misión.
  final String id;

  /// Código de la plantilla.
  final String codigoPlantilla;

  /// Título ya interpolado.
  final String titulo;

  /// Avance tras la acción.
  final int progreso;

  /// Objetivo de la misión.
  final int meta;

  /// Estado tras la acción.
  final EstadoMision estado;

  /// ¿El servidor ya entregó la recompensa?
  final bool reclamadaAuto;

  /// Qué entrega.
  final RecompensaSimple recompensa;

  /// ¿Se completó con esta acción?
  bool get seCompleto =>
      estado == EstadoMision.completada || estado == EstadoMision.reclamada;

  /// Progreso entre 0 y 1.
  double get fraccion => meta <= 0 ? 0 : (progreso / meta).clamp(0, 1).toDouble();
}

/// Logro desbloqueado por la acción (`receipt.achievements`).
class LogroRecibo {
  const LogroRecibo({
    this.codigo = '',
    this.nombre = '',
    this.nivel = NivelLogro.bronce,
    this.recompensa = const RecompensaSimple(),
    this.iconoKey,
    this.descripcion,
  });

  /// Lee `{code, name, tier, reward}`.
  factory LogroRecibo.desdeJson(Map<String, dynamic> json) => LogroRecibo(
        codigo: _txt(json['code']),
        nombre: _txt(json['name']),
        nivel: NivelLogro.desdeApi(json['tier']),
        recompensa:
            RecompensaSimple.desdeCampo(json['reward']) ?? const RecompensaSimple(),
        iconoKey: _txtN(json['icon_key']),
        descripcion: _txtN(json['description']),
      );

  /// Código del logro.
  final String codigo;

  /// Nombre visible.
  final String nombre;

  /// Nivel desbloqueado.
  final NivelLogro nivel;

  /// Qué entrega.
  final RecompensaSimple recompensa;

  /// Medalla.
  final String? iconoKey;

  /// Descripción corta.
  final String? descripcion;
}

/// Ítem entregado por la acción (`receipt.items`).
class ItemRecibo {
  const ItemRecibo({
    this.itemUsuarioId = '',
    this.codigoItem = '',
    this.nombre = '',
    this.ranura = RanuraItem.accesorio,
    this.rareza = RarezaItem.comun,
    this.origen = OrigenItem.logro,
    this.motivoDesbloqueo,
    this.puedeEquipar = true,
    this.iconoKey,
    this.capas = const <CapaAvatar>[],
    this.itemId,
  });

  /// Lee `{user_item_id, item_code, name, slot, rarity, origin, …}`.
  factory ItemRecibo.desdeJson(Map<String, dynamic> json) {
    final List<CapaAvatar> capas = _lista(json['layers'], CapaAvatar.desdeJson)
      ..sort((CapaAvatar a, CapaAvatar b) => a.z.compareTo(b.z));
    return ItemRecibo(
      itemUsuarioId: _txt(json['user_item_id']),
      codigoItem: _txt(_alguna(json, <String>['item_code', 'code'])),
      nombre: _txt(json['name']),
      ranura: RanuraItem.desdeApi(json['slot']),
      rareza: RarezaItem.desdeApi(json['rarity']),
      origen: OrigenItem.desdeApi(json['origin']),
      motivoDesbloqueo: _txtN(json['unlock_reason']),
      puedeEquipar: _bol(json['can_equip'], true),
      iconoKey: _txtN(json['icon_key']),
      capas: List<CapaAvatar>.unmodifiable(capas),
      itemId: _txtN(json['item_id']),
    );
  }

  /// Instancia poseída, lista para equipar desde el overlay.
  final String itemUsuarioId;

  /// Código del ítem del catálogo.
  final String codigoItem;

  /// Nombre visible.
  final String nombre;

  /// Ranura que ocupa.
  final RanuraItem ranura;

  /// Rareza, que decide el color del marco.
  final RarezaItem rareza;

  /// De dónde vino.
  final OrigenItem origen;

  /// Por qué se desbloqueó ("Completaste tu primera lección").
  final String? motivoDesbloqueo;

  /// ¿Se puede equipar ya?
  final bool puedeEquipar;

  /// Icono del ítem.
  final String? iconoKey;

  /// Capas para la vista previa del avatar.
  final List<CapaAvatar> capas;

  /// Identificador del ítem del catálogo.
  final String? itemId;
}

/// Algo que quedó desbloqueado (`receipt.unlocks`).
class Desbloqueo {
  const Desbloqueo({
    this.tipo = TipoDesbloqueo.otro,
    this.id = '',
    this.nombre = '',
  });

  /// Lee `{type, id, name}`.
  factory Desbloqueo.desdeJson(Map<String, dynamic> json) => Desbloqueo(
        tipo: TipoDesbloqueo.desdeApi(json['type']),
        id: _txt(json['id']),
        nombre: _txt(json['name']),
      );

  /// Qué se desbloqueó.
  final TipoDesbloqueo tipo;

  /// Identificador del elemento.
  final String id;

  /// Nombre visible.
  final String nombre;
}

/// Recibo canónico de recompensas (§7.10).
///
/// Todas las secciones existen siempre; las vacías llegan como `null` o `[]`.
/// El cliente **anima estrictamente** en el orden de [ordenPresentacion] y
/// nunca infiere: si `nivel.subioNivel` es `false`, no hay overlay de nivel.
class ReciboRecompensas {
  const ReciboRecompensas({
    this.id = '',
    this.tipoEvento = '',
    this.ocurridoEn,
    this.versionConfig = 0,
    this.xp,
    this.oro,
    this.nivel,
    this.conocimiento,
    this.deltasDominio = const <DeltaDominio>[],
    this.racha,
    this.objetivoDiario,
    this.misiones = const <MisionRecibo>[],
    this.logros = const <LogroRecibo>[],
    this.items = const <ItemRecibo>[],
    this.desbloqueos = const <Desbloqueo>[],
    this.resultadoEvaluacion,
    this.ordenPresentacion = PasoCelebracion.ordenCanonico,
    this.sincronizacionPendiente = false,
  });

  /// Lee el `RewardsReceipt` completo, venga suelto o bajo `rewards`.
  factory ReciboRecompensas.desdeJson(Map<String, dynamic> json) {
    final Map<String, dynamic> m =
        json['rewards'] is Map ? _mapa(json['rewards']) : json;
    final List<PasoCelebracion> orden = <PasoCelebracion>[];
    final Object? crudoOrden = m['presentation_order'];
    if (crudoOrden is List) {
      for (final Object? bruto in crudoOrden) {
        final PasoCelebracion? paso = PasoCelebracion.desdeApi(bruto);
        if (paso != null && !orden.contains(paso)) orden.add(paso);
      }
    }
    final Map<String, dynamic>? objetivo = _mapaN(m['daily_goal']);
    return ReciboRecompensas(
      id: _txt(_alguna(m, <String>['receipt_id', 'id'])),
      tipoEvento: _txt(m['event_type']),
      ocurridoEn: fechaHora(m['occurred_at']),
      versionConfig: _ent(m['config_version']),
      xp: m['xp'] is Map ? XpRecibo.desdeJson(_mapa(m['xp'])) : null,
      oro: m['gold'] is Map ? OroRecibo.desdeJson(_mapa(m['gold'])) : null,
      nivel: m['level'] is Map ? NivelRecibo.desdeJson(_mapa(m['level'])) : null,
      conocimiento: m['knowledge'] is Map
          ? ConocimientoRecibo.desdeJson(_mapa(m['knowledge']))
          : null,
      deltasDominio: _lista(m['mastery_deltas'], DeltaDominio.desdeJson),
      racha: m['streak'] is Map ? RachaRecibo.desdeJson(_mapa(m['streak'])) : null,
      objetivoDiario: objetivo == null || objetivo.isEmpty
          ? null
          : ObjetivoDiario.desdeJson(objetivo),
      misiones: _lista(m['missions'], MisionRecibo.desdeJson),
      logros: _lista(m['achievements'], LogroRecibo.desdeJson),
      items: _lista(m['items'], ItemRecibo.desdeJson),
      desbloqueos: _lista(m['unlocks'], Desbloqueo.desdeJson),
      resultadoEvaluacion: m['assessment_result'] is Map
          ? ResultadoEvaluacionModulo.desdeJson(_mapa(m['assessment_result']))
          : null,
      ordenPresentacion: orden.isEmpty
          ? PasoCelebracion.ordenCanonico
          : List<PasoCelebracion>.unmodifiable(orden),
      sincronizacionPendiente: _bol(m['pending_sync']),
    );
  }

  /// Identificador del recibo; repetir la petición devuelve el mismo.
  final String id;

  /// Evento que lo originó (`LESSON_COMPLETED`, `ASSESSMENT_SUBMITTED`…).
  final String tipoEvento;

  /// Cuándo ocurrió, en hora local.
  final DateTime? ocurridoEn;

  /// Versión de la configuración de juego usada.
  final int versionConfig;

  /// Desglose de XP.
  final XpRecibo? xp;

  /// Oro otorgado y saldo posterior.
  final OroRecibo? oro;

  /// Cambio de nivel global.
  final NivelRecibo? nivel;

  /// Efecto sobre el conocimiento.
  final ConocimientoRecibo? conocimiento;

  /// Variaciones de dominio por tema, módulo o ruta.
  final List<DeltaDominio> deltasDominio;

  /// Efecto sobre la racha.
  final RachaRecibo? racha;

  /// Estado del objetivo diario tras la acción.
  final ObjetivoDiario? objetivoDiario;

  /// Misiones que avanzaron o se completaron.
  final List<MisionRecibo> misiones;

  /// Logros desbloqueados.
  final List<LogroRecibo> logros;

  /// Ítems entregados.
  final List<ItemRecibo> items;

  /// Módulos, territorios o desafíos desbloqueados.
  final List<Desbloqueo> desbloqueos;

  /// Solo se rellena al enviar un intento de evaluación.
  final ResultadoEvaluacionModulo? resultadoEvaluacion;

  /// Orden autoritativo de la cola de celebraciones.
  final List<PasoCelebracion> ordenPresentacion;

  /// `true` si alguna recompensa quedó en reintento en segundo plano.
  final bool sincronizacionPendiente;

  /// ¿Este paso tiene contenido que mostrar?
  bool tienePaso(PasoCelebracion paso) => switch (paso) {
        PasoCelebracion.xp => (xp?.hayAlgo ?? false),
        PasoCelebracion.oro => (oro?.hayAlgo ?? false),
        PasoCelebracion.dominio =>
          deltasDominio.isNotEmpty || (conocimiento?.delta ?? 0) != 0,
        PasoCelebracion.racha => racha?.esPrimeraActividadDelDia ?? false,
        PasoCelebracion.subidaNivel => nivel?.subioNivel ?? false,
        PasoCelebracion.item => items.isNotEmpty,
        PasoCelebracion.logro => logros.isNotEmpty,
        PasoCelebracion.mision =>
          misiones.any((MisionRecibo m) => m.seCompleto),
      };

  /// Pasos con contenido, en el orden que manda el servidor.
  List<PasoCelebracion> get pasos =>
      ordenPresentacion.where(tienePaso).toList(growable: false);

  /// Los overlays a pantalla completa: como máximo tres (§7.10 regla 2).
  List<PasoCelebracion> get overlays => pasos
      .where(PasoCelebracion.deOverlay.contains)
      .take(3)
      .toList(growable: false);

  /// El resto se muestra como chips en la pantalla de resumen.
  List<PasoCelebracion> get chips {
    final List<PasoCelebracion> enOverlay = overlays;
    return pasos
        .where((PasoCelebracion p) => !enOverlay.contains(p))
        .toList(growable: false);
  }

  /// Misiones que se completaron con esta acción.
  List<MisionRecibo> get misionesCumplidas =>
      misiones.where((MisionRecibo m) => m.seCompleto).toList(growable: false);

  /// Delta de dominio del tema, que es el que se muestra en el resumen.
  DeltaDominio? get dominioDelTema {
    for (final DeltaDominio d in deltasDominio) {
      if (d.ambito == AmbitoDominio.tema) return d;
    }
    return deltasDominio.isEmpty ? null : deltasDominio.first;
  }

  /// Primer ítem entregado, el del overlay "Nuevo equipamiento".
  ItemRecibo? get itemDestacado => items.isEmpty ? null : items.first;

  /// Primer logro desbloqueado.
  LogroRecibo? get logroDestacado => logros.isEmpty ? null : logros.first;

  /// ¿El recibo no trae nada que celebrar?
  bool get estaVacio => pasos.isEmpty;
}
