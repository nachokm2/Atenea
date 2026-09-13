/// Repositorios de la API de Atenea: un objeto por dominio del contrato.
///
/// Reglas que se cumplen sin excepción en este archivo:
///
/// - Todo el tráfico pasa por [ApiClient]; aquí nunca se usa Dio directamente.
/// - Cada método devuelve un DTO tipado de `dtos.dart`, nunca un `Map`.
/// - Las rutas son relativas a `Entorno.apiBase`, que ya incluye `/api/v1`.
/// - Las claves JSON que se envían son literalmente las del contrato
///   (`snake_case`); los enums viajan por su valor (`ClaveApi.api`).
/// - Las rutas marcadas con **Idempotency-Key** en §8.3 reciben una clave
///   UUID v4. Quien reintente una acción debe **reutilizar la misma clave**:
///   por eso todos esos métodos aceptan `clave` y solo generan una nueva si
///   no se les pasa ninguna.
/// - La app nunca calcula XP, oro, nivel, dominio ni precios: los toma del
///   [ReciboRecompensas] y de las respuestas del servidor.
library;

import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

import '../data/api_client.dart';
import 'dtos.dart';

export 'dtos.dart';

// ---------------------------------------------------------------------------
// El sobre de una respuesta
// ---------------------------------------------------------------------------

/// Envuelve lo que el aprendiz respondió en el objeto que espera el Reino.
///
/// El contrato (§7.6 `AnswerIn`, §7.7 `AssessmentAnswerIn`) declara `response`
/// como un **objeto**, y el corrector de cada tipo busca dentro una clave
/// concreta: `option_ids` para la selección, `blanks` para los huecos, `order`
/// para la secuencia, `pairs` para las parejas, `sql` para la consulta. Mandar
/// el valor pelado (una lista, un texto, un booleano) hace que el servidor
/// responda 422 antes de mirar nada.
///
/// Las pantallas siguen trabajando con el valor natural de cada tipo; la
/// traducción a la forma del contrato vive aquí y en un solo sitio.
///
/// Si quien llama ya construyó el objeto con una de las claves conocidas, se
/// respeta tal cual: así una pantalla puede mandar `{'text': …, 'hint': …}` sin
/// que esta función se lo deshaga.
Map<String, dynamic> sobreDeRespuesta(TipoPregunta tipo, Object? valor) {
  if (valor is Map) {
    final Map<String, dynamic> mapa = Map<String, dynamic>.from(valor);
    final bool yaEsSobre = mapa.keys.any(_clavesDeRespuesta.contains);
    if (yaEsSobre) return mapa;
    if (tipo == TipoPregunta.relacionar) {
      return <String, dynamic>{'pairs': mapa};
    }
    return mapa;
  }

  List<dynamic> comoLista(Object? v) {
    if (v == null) return const <dynamic>[];
    if (v is List) return v;
    if (v is Set) return v.toList();
    return <dynamic>[v];
  }

  switch (tipo) {
    case TipoPregunta.opcionMultiple:
      return <String, dynamic>{'option_ids': comoLista(valor)};
    case TipoPregunta.verdaderoFalso:
      return <String, dynamic>{'value': valor};
    case TipoPregunta.completar:
      return <String, dynamic>{'blanks': comoLista(valor)};
    case TipoPregunta.ordenar:
      return <String, dynamic>{'order': comoLista(valor)};
    case TipoPregunta.relacionar:
      return <String, dynamic>{'pairs': valor ?? <String, dynamic>{}};
    case TipoPregunta.ejercicioSql:
      return <String, dynamic>{'sql': (valor ?? '').toString()};
    case TipoPregunta.respuestaCorta:
    case TipoPregunta.casoEstudio:
    case TipoPregunta.ejercicioCodigo:
      return <String, dynamic>{'text': (valor ?? '').toString()};
  }
}

/// Claves que el corrector del Reino reconoce dentro de `response`.
const Set<String> _clavesDeRespuesta = <String>{
  'option_ids',
  'option_id',
  'selected',
  'value',
  'answer',
  'answers',
  'blanks',
  'values',
  'pairs',
  'matches',
  'order',
  'sequence',
  'text',
  'sql',
  'query',
};

// ---------------------------------------------------------------------------
// Idempotencia y utilidades de consulta
// ---------------------------------------------------------------------------

final Random _azar = Random.secure();

/// Genera una clave de idempotencia UUID v4 (§8.3).
///
/// Se crea una por **acción del usuario**, no por petición: si la petición
/// falla y se reintenta, hay que enviar exactamente la misma clave para que el
/// servidor devuelva el mismo `receipt_id` sin volver a otorgar nada.
String claveIdempotencia() {
  final List<int> bytes = List<int>.generate(16, (_) => _azar.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // versión 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variante RFC 4122
  return _formatearUuid(bytes);
}

/// Clave determinista para una acción repetible del cliente.
///
/// Útil cuando una misma acción se puede repetir sin ambigüedad, por ejemplo
/// reabrir la misma lección: la clave se deriva del identificador y no de un
/// azar, de modo que reintentar jamás duplica.
///
/// Tiene que ser un **UUID**, no un texto legible. El contrato (§8.3) lo exige
/// y el servidor rechaza con 400 cualquier otra cosa, así que la versión
/// anterior, que devolvía `"lesson-start:<id>:1"`, hacía que empezar una
/// lección, responder, cerrarla, evaluar y reclamar una misión fallaran todas
/// desde la app. Se deriva con UUID v5, que es determinista por definición: la
/// misma acción sobre la misma entidad produce siempre la misma clave, y dos
/// acciones distintas no colisionan.
String claveDeterminista(String accion, String entidadId, [int secuencia = 1]) =>
    _uuidV5(_espacioAtenea, '$accion:$entidadId:$secuencia');

/// Espacio de nombres propio de Atenea, derivado a su vez del espacio DNS de
/// la RFC 4122 sobre `atenea.cl`. Fijarlo aquí garantiza que la clave de una
/// acción no cambie nunca entre versiones de la app.
final List<int> _espacioAtenea =
    _bytesV5(_espacioDns, 'atenea.cl');

/// Espacio de nombres DNS de la RFC 4122: `6ba7b810-9dad-11d1-80b4-00c04fd430c8`.
const List<int> _espacioDns = <int>[
  0x6b, 0xa7, 0xb8, 0x10, 0x9d, 0xad, 0x11, 0xd1, //
  0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8,
];

/// Los dieciséis bytes de un UUID v5 (SHA-1 del espacio más el nombre).
List<int> _bytesV5(List<int> espacio, String nombre) {
  final List<int> resumen =
      sha1.convert(<int>[...espacio, ...utf8.encode(nombre)]).bytes;
  final List<int> bytes = resumen.sublist(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x50; // versión 5
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variante RFC 4122
  return bytes;
}

String _uuidV5(List<int> espacio, String nombre) =>
    _formatearUuid(_bytesV5(espacio, nombre));

String _formatearUuid(List<int> bytes) {
  final StringBuffer sb = StringBuffer();
  for (int i = 0; i < 16; i++) {
    if (i == 4 || i == 6 || i == 8 || i == 10) sb.write('-');
    sb.write(bytes[i].toRadixString(16).padLeft(2, '0'));
  }
  return sb.toString();
}

/// Construye los parámetros de consulta descartando los valores nulos.
Map<String, dynamic> _consulta(Map<String, Object?> pares) {
  final Map<String, dynamic> salida = <String, dynamic>{};
  pares.forEach((String clave, Object? valor) {
    if (valor == null) return;
    if (valor is String && valor.isEmpty) return;
    salida[clave] = valor;
  });
  return salida;
}

/// Construye un cuerpo JSON descartando los valores nulos.
Map<String, dynamic> _cuerpo(Map<String, Object?> pares) {
  final Map<String, dynamic> salida = <String, dynamic>{};
  pares.forEach((String clave, Object? valor) {
    if (valor != null) salida[clave] = valor;
  });
  return salida;
}

/// Ámbito de la lista de rutas (`scope=mine|seed|all`).
enum AmbitoRutas with ClaveApi {
  mias('mine', 'Mis rutas'),
  delReino('seed', 'Rutas del Reino'),
  todas('all', 'Todas');

  const AmbitoRutas(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la pestaña.
  final String etiqueta;
}

/// Filtro de la sala de trofeos (`state=all|unlocked|in_progress`).
enum FiltroLogros with ClaveApi {
  todos('all', 'Todos'),
  desbloqueados('unlocked', 'Desbloqueados'),
  enProgreso('in_progress', 'En progreso');

  const FiltroLogros(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del filtro.
  final String etiqueta;
}

/// Ajuste de un tema al confirmar el esquema de la ruta (P07 revisión).
class AjusteTema {
  const AjusteTema({
    required this.temaId,
    this.titulo,
    this.posicion,
    this.eliminado = false,
  });

  /// Tema que se reordena, renombra o elimina.
  final String temaId;

  /// Nuevo título, si se renombra.
  final String? titulo;

  /// Nueva posición, si se reordena.
  final int? posicion;

  /// `true` para quitarlo del esquema.
  final bool eliminado;

  /// Cuerpo que espera `POST /paths/{id}/confirm`.
  Map<String, dynamic> aJson() => _cuerpo(<String, Object?>{
        'topic_id': temaId,
        'title': titulo,
        'position': posicion,
        'removed': eliminado ? true : null,
      });
}

// ---------------------------------------------------------------------------
// §7.1 Autenticación y cuenta
// ---------------------------------------------------------------------------

/// Registro, sesión, cuenta y preferencias (`identity`).
class RepoAuth {
  const RepoAuth(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Crea la cuenta con correo y contraseña (P02). No pide nombre.
  Future<TokensAuth> registrar({
    required String correo,
    required String contrasena,
    String? zonaHoraria,
    String? idioma,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/auth/register',
      sinAuth: true,
      cuerpo: _cuerpo(<String, Object?>{
        'email': correo.trim(),
        'password': contrasena,
        'timezone': zonaHoraria,
        'locale': idioma,
      }),
    );
    return TokensAuth.desdeJson(r);
  }

  /// Inicia sesión.
  Future<TokensAuth> entrar({
    required String correo,
    required String contrasena,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/auth/login',
      sinAuth: true,
      cuerpo: <String, dynamic>{
        'email': correo.trim(),
        'password': contrasena,
      },
    );
    return TokensAuth.desdeJson(r);
  }

  /// Rota el par de tokens. El [ApiClient] ya lo hace solo ante un 401; este
  /// método existe para el arranque de la app.
  Future<TokensAuth> refrescar(String refresco) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/auth/refresh',
      sinAuth: true,
      cuerpo: <String, dynamic>{'refresh_token': refresco},
    );
    return TokensAuth.desdeJson(r);
  }

  /// Revoca el refresh token recibido.
  Future<void> salir(String refresco) => cliente.enviar(
        '/auth/logout',
        cuerpo: <String, dynamic>{'refresh_token': refresco},
      );

  /// Usuario, personaje y estado de onboarding.
  Future<Yo> yo() async => Yo.desdeJson(await cliente.obtener('/auth/me'));

  /// Cambia la contraseña; el servidor revoca todas las sesiones.
  Future<void> cambiarContrasena({
    required String actual,
    required String nueva,
  }) =>
      cliente.enviar(
        '/auth/password',
        cuerpo: <String, dynamic>{
          'current_password': actual,
          'new_password': nueva,
        },
      );

  /// Pide el enlace para elegir una contraseña nueva.
  ///
  /// El Reino responde igual exista o no la cuenta: si respondiera distinto,
  /// este formulario sería una lista de cuentas válidas que cualquiera podría
  /// consultar. Por eso aquí tampoco hay nada que interpretar.
  Future<void> pedirRecuperacion(String correo) => cliente.enviar(
        '/auth/password/forgot',
        sinAuth: true,
        cuerpo: <String, dynamic>{'email': correo.trim()},
      );

  /// Elige la contraseña nueva con el permiso que llegó por correo.
  Future<void> restablecerContrasena({
    required String permiso,
    required String nueva,
  }) =>
      cliente.enviar(
        '/auth/password/reset',
        sinAuth: true,
        cuerpo: <String, dynamic>{'token': permiso, 'new_password': nueva},
      );

  /// Borrado lógico de la cuenta y de sus documentos.
  Future<void> eliminarCuenta() => cliente.eliminar('/auth/account');

  /// Preferencias del usuario (P21).
  Future<Ajustes> ajustes() async =>
      Ajustes.desdeJson(await cliente.obtener('/settings'));

  /// Actualiza solo las preferencias que se pasan; el resto no se toca.
  Future<Ajustes> actualizarAjustes({
    PreferenciaTema? tema,
    bool? reducirMovimiento,
    bool? sonidoActivado,
    bool? hapticaActivada,
    bool? pushActivado,
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
  }) async {
    final Map<String, dynamic> r = await cliente.actualizar(
      '/settings',
      parcial: false,
      cuerpo: _cuerpo(<String, Object?>{
        'theme': tema?.api,
        'reduce_motion': reducirMovimiento,
        'sound_enabled': sonidoActivado,
        'haptics_enabled': hapticaActivada,
        'push_enabled': pushActivado,
        'reminder_mode': modoRecordatorio?.api,
        'reminder_time_local': horaRecordatorio?.texto,
        'last_call_enabled': ultimaLlamadaActivada,
        'quiet_hours_start': silencioDesde?.texto,
        'quiet_hours_end': silencioHasta?.texto,
        'notify_path_ready': avisarRutaLista,
        'notify_streak': avisarRacha,
        'notify_missions': avisarMisiones,
        'content_language': idiomaContenido,
        'timezone': zonaHoraria,
        'locale': idioma,
      }),
    );
    return Ajustes.desdeJson(r);
  }
}

// ---------------------------------------------------------------------------
// §7.2 Personaje, avatar e inventario
// ---------------------------------------------------------------------------

/// Personaje y avatar (`identity`).
class RepoPersonaje {
  const RepoPersonaje(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Crea el personaje (P03). Devuelve el personaje con su [ReciboRecompensas]
  /// en `recompensas`: la bolsa de bienvenida y el kit inicial.
  Future<Personaje> crear({
    required String nombre,
    required Arquetipo arquetipo,
    TipoCuerpo? tipoCuerpo,
    String? tonoPiel,
    String? rostro,
    String? orejas,
    String? cabello,
    String? colorCabello,
    FormaTrato? formaTrato,
    String? clave,
  }) async {
    final Map<String, dynamic> rasgos = _cuerpo(<String, Object?>{
      'body_type': tipoCuerpo?.api,
      'skin_tone': tonoPiel,
      'face_id': rostro,
      'ear_style': orejas,
      'hair_style_id': cabello,
      'hair_color': colorCabello,
      'address_form': formaTrato?.api,
    });
    final Map<String, dynamic> r = await cliente.enviar(
      '/characters',
      claveIdempotencia: clave ?? claveIdempotencia(),
      cuerpo: _cuerpo(<String, Object?>{
        'name': nombre.trim(),
        'archetype': arquetipo.api,
        'traits': rasgos.isEmpty ? null : rasgos,
      }),
    );
    return Personaje.desdeJson(r);
  }

  /// Personaje con nivel, XP, rango y contadores.
  Future<Personaje> mio() async =>
      Personaje.desdeJson(await cliente.obtener('/characters/me'));

  /// Renombra el personaje o cambia la Orden (gratis en el MVP).
  Future<Personaje> actualizar({String? nombre, Arquetipo? arquetipo}) async {
    final Map<String, dynamic> r = await cliente.actualizar(
      '/characters/me',
      cuerpo: _cuerpo(<String, Object?>{
        'name': nombre?.trim(),
        'archetype': arquetipo?.api,
      }),
    );
    return Personaje.desdeJson(r);
  }

  /// Rasgos, Orden, equipo y manifiesto de capas ya ordenado por z.
  Future<Avatar> avatar() async =>
      Avatar.desdeJson(await cliente.obtener('/avatar'));

  /// Cambia piel, rostro, orejas, cabello, color y forma de tratamiento.
  Future<Avatar> cambiarRasgos({
    TipoCuerpo? tipoCuerpo,
    String? tonoPiel,
    String? rostro,
    String? orejas,
    String? cabello,
    String? colorCabello,
    FormaTrato? formaTrato,
    String? colorAcento,
  }) async {
    final Map<String, dynamic> r = await cliente.actualizar(
      '/avatar/traits',
      parcial: false,
      cuerpo: _cuerpo(<String, Object?>{
        'body_type': tipoCuerpo?.api,
        'skin_tone': tonoPiel,
        'face_id': rostro,
        'ear_style': orejas,
        'hair_style_id': cabello,
        'hair_color': colorCabello,
        'address_form': formaTrato?.api,
        'accent_color': colorAcento,
      }),
    );
    return Avatar.desdeJson(r);
  }

  /// Equipa o quita ítems de forma atómica: `{"weapon": "<id>", "cape": null}`.
  ///
  /// Las claves son el valor de [RanuraItem.api] y el valor es el
  /// `user_item_id`, o `null` para dejar la ranura vacía.
  Future<Avatar> cambiarEquipo(Map<RanuraItem, String?> equipo) async {
    final Map<String, dynamic> ranuras = <String, dynamic>{};
    equipo.forEach((RanuraItem ranura, String? itemUsuarioId) {
      ranuras[ranura.api] = itemUsuarioId;
    });
    final Map<String, dynamic> r = await cliente.actualizar(
      '/avatar/equipment',
      parcial: false,
      // El mapa viaja **envuelto** en `equipment`, como declara el contrato
      // (§7.8 `AvatarEquipmentIn`). Mandarlo plano daba 422 en toda petición,
      // así que equipar no funcionaba desde ninguna pantalla.
      cuerpo: <String, dynamic>{'equipment': ranuras},
    );
    return Avatar.desdeJson(r);
  }
}

/// Inventario y fichas de ítems (`economy`).
class RepoInventario {
  const RepoInventario(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Poseídos más bloqueados visibles, con el progreso de sus requisitos (P16).
  Future<Pagina<ItemInventario>> inventario({
    RanuraItem? ranura,
    RarezaItem? rareza,
    OrigenItem? origen,
    String? estado,
    int limite = 30,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/inventory',
      consulta: _consulta(<String, Object?>{
        'slot': ranura?.api,
        'rarity': rareza?.api,
        'origin': origen?.api,
        'state': estado,
        'limit': limite,
        'cursor': cursor,
      }),
    );
    return Pagina<ItemInventario>.desdeJson(r, ItemInventario.desdeJson);
  }

  /// Ficha del ítem: lore, rareza, origen y explicación de sus requisitos.
  Future<DetalleItem> item(String itemId) async =>
      DetalleItem.desdeJson(await cliente.obtener('/items/$itemId'));

  /// Registra `ITEM_PREVIEWED` al pulsar "Probar" (analítica).
  Future<void> registrarPrueba(String itemId) =>
      cliente.enviar('/items/$itemId/preview');
}

// ---------------------------------------------------------------------------
// §7.3 Tienda
// ---------------------------------------------------------------------------

/// Mercado y monedero (`economy`).
class RepoTienda {
  const RepoTienda(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Catálogo activo, destacados, saldo y "Se ganan aprendiendo" (P15).
  Future<Tienda> tienda() async =>
      Tienda.desdeJson(await cliente.obtener('/shop'));

  /// Compra atómica. `precioEsperado` protege de un cambio de precio.
  ///
  /// Reintentar con la misma [clave] devuelve la misma compra sin cobrar dos
  /// veces (§8.3).
  Future<Compra> comprar({
    required String anuncioId,
    required int precioEsperado,
    String? clave,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/shop/purchase',
      claveIdempotencia: clave ?? claveIdempotencia(),
      cuerpo: <String, dynamic>{
        'listing_id': anuncioId,
        'expected_price': precioEsperado,
      },
    );
    return Compra.desdeJson(r);
  }

  /// "Deshacer" dentro de `shop.purchase_reversal_seconds`.
  Future<Compra> deshacerCompra(String compraId) async => Compra.desdeJson(
        await cliente.enviar('/shop/purchases/$compraId/reverse'),
      );

  /// Saldo, totales de por vida y últimos movimientos de oro.
  Future<Monedero> monedero({int limite = 20, String? cursor}) async =>
      Monedero.desdeJson(
        await cliente.obtener(
          '/wallet',
          consulta: _consulta(<String, Object?>{
            'limit': limite,
            'cursor': cursor,
          }),
        ),
      );
}

// ---------------------------------------------------------------------------
// §7.4 Conocimientos y mundo
// ---------------------------------------------------------------------------

/// Conocimientos, dominio y territorios (`content` + `progress`).
class RepoConocimiento {
  const RepoConocimiento(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Catálogo canónico más las áreas del usuario, con su dominio si existe.
  Future<Pagina<AreaConocimiento>> areas({
    int limite = 30,
    String? cursor,
    CategoriaConocimiento? categoria,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/knowledge-areas',
      consulta: _consulta(<String, Object?>{
        'limit': limite,
        'cursor': cursor,
        'category': categoria?.api,
      }),
    );
    return Pagina<AreaConocimiento>.desdeJson(r, AreaConocimiento.desdeJson);
  }

  /// Detalle del conocimiento: nivel, XP, dominio con su explicación, tiempo,
  /// módulos y temas débiles.
  Future<DetalleAreaConocimiento> area(String areaId) async =>
      DetalleAreaConocimiento.desdeJson(
        await cliente.obtener('/knowledge-areas/$areaId'),
      );

  /// Perfil de conocimiento del usuario (P17, sección Conocimientos).
  Future<Pagina<ConocimientoUsuario>> miConocimiento({
    int limite = 30,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/me/knowledge',
      consulta: _consulta(<String, Object?>{'limit': limite, 'cursor': cursor}),
    );
    return Pagina<ConocimientoUsuario>.desdeJson(r, ConocimientoUsuario.desdeJson);
  }

  /// Mapa simplificado del Reino (P22): territorios y zonas desbloqueadas.
  Future<Pagina<Territorio>> territorios({
    int limite = 50,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/territories',
      consulta: _consulta(<String, Object?>{'limit': limite, 'cursor': cursor}),
    );
    return Pagina<Territorio>.desdeJson(r, Territorio.desdeJson);
  }
}

// ---------------------------------------------------------------------------
// §7.5 Rutas de aprendizaje y material
// ---------------------------------------------------------------------------

/// Rutas del usuario y Rutas del Reino (`content` + `ai`).
class RepoRutas {
  const RepoRutas(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Mis rutas más las Rutas del Reino (P22).
  Future<Pagina<ResumenRuta>> rutas({
    AmbitoRutas ambito = AmbitoRutas.todas,
    int limite = 20,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/paths',
      consulta: _consulta(<String, Object?>{
        'scope': ambito.api,
        'limit': limite,
        'cursor': cursor,
      }),
    );
    return Pagina<ResumenRuta>.desdeJson(r, ResumenRuta.desdeJson);
  }

  /// Crea la ruta (P05) y encola la Fase A del diseño.
  Future<RutaCreada> crear({
    required String objetivo,
    required NivelDeclarado nivelDeclarado,
    List<String> documentos = const <String>[],
    ModoFuente modoFuente = ModoFuente.sinFuente,
    String? pistaConocimiento,
    String? clave,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/paths',
      claveIdempotencia: clave ?? claveIdempotencia(),
      tiempoLimite: const Duration(seconds: 90),
      cuerpo: _cuerpo(<String, Object?>{
        'goal_text': objetivo.trim(),
        'declared_level': nivelDeclarado.api,
        'document_ids': documentos,
        'source_mode': modoFuente.api,
        'knowledge_area_hint': pistaConocimiento,
      }),
    );
    return RutaCreada.desdeJson(r);
  }

  /// Mapa de la ruta (P07): módulos, temas, lecciones y bloqueos.
  Future<DetalleRuta> ruta(String rutaId) async =>
      DetalleRuta.desdeJson(await cliente.obtener('/paths/$rutaId'));

  /// Confirma el esquema revisado y encola el módulo 1.
  Future<DetalleRuta> confirmar(
    String rutaId, {
    List<AjusteTema> temas = const <AjusteTema>[],
    PoliticaCobertura? politicaCobertura,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/paths/$rutaId/confirm',
      cuerpo: _cuerpo(<String, Object?>{
        'topics': temas.isEmpty
            ? null
            : temas.map((AjusteTema t) => t.aJson()).toList(growable: false),
        'coverage_policy': politicaCobertura?.api,
      }),
    );
    return DetalleRuta.desdeJson(r);
  }

  /// Renombra o archiva la ruta.
  Future<DetalleRuta> actualizar(
    String rutaId, {
    String? titulo,
    bool? archivada,
  }) async {
    final Map<String, dynamic> r = await cliente.actualizar(
      '/paths/$rutaId',
      cuerpo: _cuerpo(<String, Object?>{
        'title': titulo?.trim(),
        'archived': archivada,
      }),
    );
    return DetalleRuta.desdeJson(r);
  }

  /// Elimina la ruta y cancela sus misiones de ruta.
  Future<void> eliminar(String rutaId) => cliente.eliminar('/paths/$rutaId');

  /// Adopta una Ruta del Reino sin duplicar contenido.
  Future<DetalleRuta> adoptar(String rutaId) async =>
      DetalleRuta.desdeJson(await cliente.enviar('/paths/$rutaId/adopt'));

  /// Estado agregado de la generación (P06). Se consulta cada 2–3 s.
  Future<EstadoGeneracion> generacion(String rutaId) async =>
      EstadoGeneracion.desdeJson(
        await cliente.obtener('/paths/$rutaId/generation'),
      );

  /// Documentos que respaldan la ruta.
  Future<Pagina<Documento>> fuentes(
    String rutaId, {
    int limite = 20,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/paths/$rutaId/sources',
      consulta: _consulta(<String, Object?>{'limit': limite, 'cursor': cursor}),
    );
    return Pagina<Documento>.desdeJson(r, Documento.desdeJson);
  }
}

/// Material del usuario: subida, ingesta y fragmentos (`ingestion`).
class RepoDocumentos {
  const RepoDocumentos(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Sube un archivo (PDF, DOCX, MD, TXT) y encola la ingesta.
  ///
  /// [alProgresar] recibe los bytes enviados y el total, para la barra de
  /// progreso de P05.
  Future<Documento> subir({
    required List<int> bytes,
    required String nombreArchivo,
    String? titulo,
    String? clave,
    void Function(int enviados, int total)? alProgresar,
  }) async {
    final Map<String, dynamic> r = await cliente.subirArchivo(
      '/documents',
      bytes: bytes,
      nombreArchivo: nombreArchivo,
      alProgresar: alProgresar,
      campos: _cuerpo(<String, Object?>{'title': titulo?.trim()}),
      claveIdempotencia: clave ?? claveIdempotencia(),
    );
    return Documento.desdeJson(r);
  }

  /// Pega texto como material de estudio.
  Future<Documento> pegar({
    required String titulo,
    required String texto,
    String? clave,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/documents/paste',
      claveIdempotencia: clave ?? claveIdempotencia(),
      cuerpo: <String, dynamic>{
        'title': titulo.trim(),
        'text': texto,
      },
    );
    return Documento.desdeJson(r);
  }

  /// Mis documentos (P21 → Datos).
  Future<Pagina<Documento>> documentos({
    int limite = 20,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/documents',
      consulta: _consulta(<String, Object?>{'limit': limite, 'cursor': cursor}),
    );
    return Pagina<Documento>.desdeJson(r, Documento.desdeJson);
  }

  /// Detalle y estado de procesamiento de un documento.
  Future<Documento> documento(String documentoId) async =>
      Documento.desdeJson(await cliente.obtener('/documents/$documentoId'));

  /// Borrado lógico con purga diferida.
  Future<void> eliminar(String documentoId) =>
      cliente.eliminar('/documents/$documentoId');

  /// Estado de un trabajo de generación o de ingesta (sondeo cada 2–3 s).
  Future<Trabajo> trabajo(String trabajoId) async =>
      Trabajo.desdeJson(await cliente.obtener('/jobs/$trabajoId'));

  /// Fragmento original para la hoja "Fuente".
  Future<Fragmento> fragmento(String fragmentoId) async =>
      Fragmento.desdeJson(await cliente.obtener('/chunks/$fragmentoId'));
}

// ---------------------------------------------------------------------------
// §7.6 Lección, respuestas y recompensas
// ---------------------------------------------------------------------------

/// Lección, actividad, respuestas, repasos y reportes (`progress` + `ai`).
class RepoLeccion {
  const RepoLeccion(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Lección completa con bloques y procedencia. Nunca trae `answer_key`.
  Future<Leccion> leccion(String leccionId) async =>
      Leccion.desdeJson(await cliente.obtener('/lessons/$leccionId'));

  /// Abre la actividad y devuelve las preguntas sin claves de corrección.
  Future<Actividad> empezar(String leccionId, {String? clave}) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/lessons/$leccionId/start',
      claveIdempotencia: clave ?? claveDeterminista('lesson-start', leccionId),
    );
    return Actividad.desdeJson(r);
  }

  /// Envía una respuesta y devuelve la corrección con su retroalimentación.
  ///
  /// [respuesta] es el valor natural del tipo: la clave elegida, la lista
  /// ordenada, el mapa de parejas o el texto libre. [sobreDeRespuesta] lo
  /// envuelve en la forma que exige el contrato, por eso hace falta [tipo].
  Future<ResultadoRespuesta> responder(
    String actividadId, {
    required String preguntaId,
    required TipoPregunta tipo,
    required Object respuesta,
    int? milisegundos,
    bool ayudaUsada = false,
    String? clave,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/activities/$actividadId/answers',
      claveIdempotencia:
          clave ?? claveDeterminista('answer:$actividadId', preguntaId),
      cuerpo: _cuerpo(<String, Object?>{
        'question_id': preguntaId,
        'response': sobreDeRespuesta(tipo, respuesta),
        'response_ms': milisegundos,
        'hint_used': ayudaUsada ? true : null,
      }),
    );
    return ResultadoRespuesta.desdeJson(r);
  }

  /// Latido de tiempo efectivo. El servidor acepta como mucho 60 s por latido.
  Future<LatidoActividad> latido(String actividadId, int segundos) async {
    final int acotado = segundos < 0 ? 0 : (segundos > 60 ? 60 : segundos);
    final Map<String, dynamic> r = await cliente.enviar(
      '/activities/$actividadId/heartbeat',
      cuerpo: <String, dynamic>{'seconds': acotado},
    );
    return LatidoActividad.desdeJson(r);
  }

  /// Cierra la actividad y devuelve el recibo canónico de recompensas (P10).
  Future<ReciboRecompensas> completar(String actividadId, {String? clave}) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/activities/$actividadId/complete',
      claveIdempotencia:
          clave ?? claveDeterminista('activity-complete', actividadId),
      tiempoLimite: const Duration(seconds: 60),
    );
    return ReciboRecompensas.desdeJson(r);
  }

  /// Marca la actividad como abandonada, sin recompensa.
  Future<void> abandonar(String actividadId) =>
      cliente.enviar('/activities/$actividadId/abandon');

  /// Repasos recomendados: temas en riesgo o débiles, con duración estimada.
  Future<Pagina<SugerenciaRepaso>> repasosRecomendados({
    int limite = 10,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/reviews/recommended',
      consulta: _consulta(<String, Object?>{'limit': limite, 'cursor': cursor}),
    );
    return Pagina<SugerenciaRepaso>.desdeJson(r, SugerenciaRepaso.desdeJson);
  }

  /// Abre un repaso de 4–8 preguntas sobre un tema.
  Future<Actividad> empezarRepaso(String temaId, {String? clave}) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/reviews/start',
      claveIdempotencia: clave ?? claveIdempotencia(),
      cuerpo: <String, dynamic>{'topic_id': temaId},
    );
    return Actividad.desdeJson(r);
  }

  /// Pide otra explicación del tema, con enfoque distinto y citas.
  Future<Explicacion> reexplicar(String temaId, {String? enfoque}) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/topics/$temaId/explain',
      tiempoLimite: const Duration(seconds: 60),
      cuerpo: _cuerpo(<String, Object?>{'approach': enfoque}),
    );
    return Explicacion.desdeJson(r);
  }

  /// Reporta un bloque o una pregunta con problemas.
  Future<void> reportar({
    required TipoContenido tipoContenido,
    required String contenidoId,
    required String motivo,
    String? comentario,
  }) =>
      cliente.enviar(
        '/content/report',
        cuerpo: _cuerpo(<String, Object?>{
          'content_type': tipoContenido.api,
          'content_id': contenidoId,
          'reason': motivo,
          'comment': comentario,
        }),
      );
}

// ---------------------------------------------------------------------------
// §7.7 Evaluación de módulo
// ---------------------------------------------------------------------------

/// Desafío del módulo: entrada, intento, respuestas y revisión (`progress`).
class RepoEvaluacion {
  const RepoEvaluacion(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Pantalla de entrada (P11): reglas, recompensa, intentos y enfriamiento.
  Future<InfoEvaluacion> info(String moduloId) async =>
      InfoEvaluacion.desdeJson(
        await cliente.obtener('/modules/$moduloId/assessment'),
      );

  /// Crea el intento y muestrea el banco de preguntas.
  Future<IntentoEvaluacion> empezar(String evaluacionId, {String? clave}) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/assessments/$evaluacionId/start',
      claveIdempotencia: clave ?? claveIdempotencia(),
    );
    return IntentoEvaluacion.desdeJson(r);
  }

  /// Registra una respuesta del intento. El feedback es mínimo, sin explicación.
  Future<RegistroRespuesta> responder(
    String intentoId, {
    required String preguntaId,
    required TipoPregunta tipo,
    required Object respuesta,
    int? milisegundos,
    String? clave,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/assessment-attempts/$intentoId/answers',
      claveIdempotencia:
          clave ?? claveDeterminista('assessment-answer:$intentoId', preguntaId),
      cuerpo: _cuerpo(<String, Object?>{
        'question_id': preguntaId,
        'response': sobreDeRespuesta(tipo, respuesta),
        'response_ms': milisegundos,
      }),
    );
    return RegistroRespuesta.desdeJson(r);
  }

  /// Cierra el intento y devuelve el recibo con `assessment_result` (P12).
  Future<ReciboRecompensas> enviar(String intentoId, {String? clave}) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/assessment-attempts/$intentoId/submit',
      claveIdempotencia:
          clave ?? claveDeterminista('assessment-submit', intentoId),
      tiempoLimite: const Duration(seconds: 90),
    );
    return ReciboRecompensas.desdeJson(r);
  }

  /// Revisión de respuestas con explicación y fuente.
  Future<RevisionEvaluacion> revision(String intentoId) async =>
      RevisionEvaluacion.desdeJson(
        await cliente.obtener('/assessment-attempts/$intentoId'),
      );
}

// ---------------------------------------------------------------------------
// §7.8 Panel principal, perfil y estadísticas
// ---------------------------------------------------------------------------

/// Panel, perfil y estadísticas (`gamification` + `progress`).
class RepoPanel {
  const RepoPanel(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Todo lo que el Inicio (P04) necesita, en una sola llamada.
  Future<Panel> panel() async => Panel.desdeJson(await cliente.obtener('/dashboard'));

  /// Perfil de videojuego (P17).
  Future<Perfil> perfil() async =>
      Perfil.desdeJson(await cliente.obtener('/profile'));

  /// Estadísticas ampliadas con rango de fechas.
  Future<Estadisticas> estadisticas({DateTime? desde, DateTime? hasta}) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/profile/stats',
      consulta: _consulta(<String, Object?>{
        'from': _dia(desde),
        'to': _dia(hasta),
      }),
    );
    return Estadisticas.desdeJson(r);
  }

  /// Formatea un día de calendario como `2026-09-10`.
  static String? _dia(DateTime? fecha) {
    if (fecha == null) return null;
    final String mes = fecha.month.toString().padLeft(2, '0');
    final String dia = fecha.day.toString().padLeft(2, '0');
    return '${fecha.year}-$mes-$dia';
  }
}

// ---------------------------------------------------------------------------
// §7.9 Racha, objetivo diario, misiones, logros y notificaciones
// ---------------------------------------------------------------------------

/// Racha, objetivo diario, misiones, logros, notificaciones y configuración.
class RepoGamificacion {
  const RepoGamificacion(this.cliente);

  /// Cliente HTTP compartido.
  final ApiClient cliente;

  /// Racha actual, mejor, estado y próximo hito con su recompensa (P18).
  Future<Racha> racha() async => Racha.desdeJson(await cliente.obtener('/streak'));

  /// Calendario mensual de la racha. [mes] va en formato `2026-09`.
  Future<CalendarioRacha> calendario({String? mes}) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/streak/calendar',
      consulta: _consulta(<String, Object?>{'month': mes}),
    );
    return CalendarioRacha.desdeJson(r);
  }

  /// Objetivo vigente, progreso de hoy y recomendación pendiente.
  Future<ObjetivoDiario> objetivoDiario() async =>
      ObjetivoDiario.desdeJson(await cliente.obtener('/daily-goal'));

  /// Cambia tipo y meta. Las subidas rigen ya; las bajadas, al día siguiente.
  Future<ObjetivoDiario> cambiarObjetivo({
    required TipoObjetivo tipo,
    required int meta,
  }) async {
    final Map<String, dynamic> r = await cliente.actualizar(
      '/daily-goal',
      parcial: false,
      cuerpo: <String, dynamic>{'type': tipo.api, 'target': meta},
    );
    return ObjetivoDiario.desdeJson(r);
  }

  /// Acepta la recomendación adaptativa del objetivo.
  Future<ObjetivoDiario> aceptarRecomendacion() async =>
      ObjetivoDiario.desdeJson(
        await cliente.enviar('/daily-goal/recommendation/accept'),
      );

  /// La rechaza; no se repite en 28 días.
  Future<void> descartarRecomendacion() =>
      cliente.enviar('/daily-goal/recommendation/dismiss');

  /// Misiones diarias, semanales y de ruta (P19).
  Future<Misiones> misiones() async =>
      Misiones.desdeJson(await cliente.obtener('/missions'));

  /// Reclama la recompensa de una misión cumplida y devuelve el recibo.
  Future<ReciboRecompensas> reclamarMision(
    String misionId, {
    String? clave,
  }) async {
    final Map<String, dynamic> r = await cliente.enviar(
      '/missions/$misionId/claim',
      claveIdempotencia: clave ?? claveDeterminista('mission-claim', misionId),
    );
    return ReciboRecompensas.desdeJson(r);
  }

  /// Sala de trofeos (P20) con progreso por nivel.
  Future<Pagina<Logro>> logros({
    FiltroLogros filtro = FiltroLogros.todos,
    CategoriaLogro? categoria,
    int limite = 40,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/achievements',
      consulta: _consulta(<String, Object?>{
        'state': filtro.api,
        'category': categoria?.api,
        'limit': limite,
        'cursor': cursor,
      }),
    );
    return Pagina<Logro>.desdeJson(r, Logro.desdeJson);
  }

  /// Bandeja de notificaciones in-app.
  Future<Pagina<Notificacion>> notificaciones({
    int limite = 20,
    String? cursor,
  }) async {
    final Map<String, dynamic> r = await cliente.obtener(
      '/notifications',
      consulta: _consulta(<String, Object?>{'limit': limite, 'cursor': cursor}),
    );
    return Pagina<Notificacion>.desdeJson(r, Notificacion.desdeJson);
  }

  /// Marca una notificación como leída.
  Future<void> marcarLeida(String notificacionId) =>
      cliente.enviar('/notifications/$notificacionId/read');

  /// Marca todas como leídas.
  Future<void> marcarTodasLeidas() => cliente.enviar('/notifications/read-all');

  /// Registra o actualiza el token de push del dispositivo.
  Future<void> registrarTokenPush(String token, {String? plataforma}) =>
      cliente.enviar(
        '/devices/push-token',
        cuerpo: _cuerpo(<String, Object?>{
          'token': token,
          'platform': plataforma,
        }),
      );

  /// Claves públicas de juego, curvas de nivel y colores de rareza.
  ///
  /// Se recarga cuando la cabecera `X-Config-Version` sube.
  Future<ConfigPublica> configPublica() async => ConfigPublica.desdeJson(
        await cliente.obtener('/config/public', sinAuth: true),
      );

  /// Salud del servicio y de la base de datos.
  Future<Salud> salud() async =>
      Salud.desdeJson(await cliente.obtener('/health', sinAuth: true));
}

// ---------------------------------------------------------------------------
// Contenedor de repositorios
// ---------------------------------------------------------------------------

/// Agrupa los once repositorios sobre un mismo [ApiClient].
///
/// Se registra una sola vez con `Provider` y cada pantalla toma el
/// repositorio que necesita.
class Repositorios {
  Repositorios(this.cliente)
      : auth = RepoAuth(cliente),
        personaje = RepoPersonaje(cliente),
        inventario = RepoInventario(cliente),
        tienda = RepoTienda(cliente),
        conocimiento = RepoConocimiento(cliente),
        rutas = RepoRutas(cliente),
        documentos = RepoDocumentos(cliente),
        leccion = RepoLeccion(cliente),
        evaluacion = RepoEvaluacion(cliente),
        panel = RepoPanel(cliente),
        gamificacion = RepoGamificacion(cliente);

  /// Cliente HTTP compartido por todos los repositorios.
  final ApiClient cliente;

  /// §7.1 Autenticación, cuenta y preferencias.
  final RepoAuth auth;

  /// §7.2 Personaje y avatar.
  final RepoPersonaje personaje;

  /// §7.2 Inventario y fichas de ítems.
  final RepoInventario inventario;

  /// §7.3 Mercado y monedero.
  final RepoTienda tienda;

  /// §7.4 Conocimientos, dominio y territorios.
  final RepoConocimiento conocimiento;

  /// §7.5 Rutas de aprendizaje.
  final RepoRutas rutas;

  /// §7.5 Material del usuario y trabajos de ingesta.
  final RepoDocumentos documentos;

  /// §7.6 Lección, respuestas, repasos y reportes.
  final RepoLeccion leccion;

  /// §7.7 Desafío del módulo.
  final RepoEvaluacion evaluacion;

  /// §7.8 Panel, perfil y estadísticas.
  final RepoPanel panel;

  /// §7.9 Racha, objetivo diario, misiones, logros y notificaciones.
  final RepoGamificacion gamificacion;
}
