@Tags(<String>['vivo'])
library;

import 'dart:io';

import 'package:atenea/data/almacen_tokens.dart';
import 'package:atenea/data/api_client.dart';
import 'package:atenea/datos/repositorios.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Recorre la API **de verdad** con los mismos repositorios y modelos que usan
/// las pantallas.
///
/// El resto de las pruebas del cliente comprueban que la interfaz se dibuja;
/// esta comprueba algo distinto, que no se ve en ninguna otra parte: que lo que
/// el cliente cree que devuelve el Reino y lo que el Reino devuelve de verdad
/// son la misma cosa. Los modelos se escribieron leyendo el contrato, no
/// respuestas reales, así que aquí aparece cualquier nombre de campo que no
/// calce.
///
/// Necesita la API levantada. Si no responde, las pruebas se saltan en vez de
/// fallar, para no romper una ejecución normal de `flutter test`:
///
///     cd backend && python -m uvicorn app.main:app --port 8000
///     flutter test test/contrato_vivo_test.dart
void main() {
  final String base =
      Platform.environment['ATENEA_API'] ?? 'http://127.0.0.1:8000/api/v1';

  late Repositorios repos;
  late AlmacenTokens tokens;
  bool apiViva = false;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    // El enlace de pruebas de Flutter sustituye el cliente HTTP por uno falso
    // que responde 400 y cuerpo vacio a *todo*, para que ninguna prueba de
    // interfaz salga a la red sin querer. Esta prueba existe justamente para
    // salir a la red, asi que hay que devolver el cliente de verdad.
    HttpOverrides.global = null;
    _almacenEnMemoria();
    tokens = AlmacenTokens();
    repos = Repositorios(ApiClient(baseUrl: base, tokens: tokens));
    try {
      final Map<String, dynamic> salud =
          await repos.cliente.obtener('/health', sinAuth: true);
      apiViva = salud['status'] == 'ok';
    } catch (_) {
      apiViva = false;
    }
  });

  String correoNuevo() =>
      'cliente-${DateTime.now().microsecondsSinceEpoch}@aprendices-atenea.cl';

  test('la configuración pública se lee sin sesión', () async {
    if (!apiViva) {
      markTestSkipped('La API no responde en $base');
      return;
    }

    final ConfigPublica config = await repos.gamificacion.configPublica();

    expect(config.valores, isNotEmpty, reason: 'sin valores no se puede dibujar');
    expect(config.niveles, isNotEmpty, reason: 'sin curva no hay barra de nivel');
    expect(config.niveles.first.tituloRango, isNotEmpty);
    expect(config.valores.containsKey('items.rarity_colors'), isTrue,
        reason: 'la app pinta la rareza con estos colores');
  });

  test('el recorrido del primer día habla el mismo idioma que el Reino',
      () async {
    if (!apiViva) {
      markTestSkipped('La API no responde en $base');
      return;
    }

    // 1 · Cuenta
    final TokensAuth sesion = await repos.auth.registrar(
      correo: correoNuevo(),
      contrasena: 'Reino2026seguro',
    );
    expect(sesion.acceso, isNotEmpty);
    await tokens.guardar(acceso: sesion.acceso, refresco: sesion.refresco);

    final Yo yo = await repos.auth.yo();
    expect(yo.tienePersonaje, isFalse);

    // 2 · Personaje
    // Ninguna llamada pasa `clave` a mano: así se ejercita la que genera la
    // app de verdad. Cuando `claveDeterminista` devolvía un texto legible en
    // vez de un UUID, esta prueba pasaba en verde y el producto respondía 400
    // a todas las acciones del bucle, porque aquí se sustituía justo el valor
    // que fallaba.
    final Personaje personaje = await repos.personaje.crear(
      nombre: 'Prueba de contrato',
      arquetipo: Arquetipo.acero,
    );
    expect(personaje.nombre, isNotEmpty);
    expect(personaje.nivel, greaterThanOrEqualTo(1));
    expect(personaje.recompensas, isNotNull,
        reason: 'la creación devuelve un ReciboRecompensas');

    // 3 · Rutas del Reino
    final Pagina<ResumenRuta> rutas =
        await repos.rutas.rutas(ambito: AmbitoRutas.todas);
    expect(rutas.elementos, isNotEmpty, reason: 'debe existir la ruta semilla');
    final ResumenRuta semilla = rutas.elementos.first;
    expect(semilla.titulo, isNotEmpty);

    // 4 · Adoptarla y leer su mapa
    await repos.rutas.adoptar(semilla.id);
    final DetalleRuta detalle = await repos.rutas.ruta(semilla.id);
    expect(detalle.modulos, isNotEmpty);
    final List<ResumenLeccion> lecciones = <ResumenLeccion>[
      for (final ModuloRuta m in detalle.modulos)
        for (final Tema t in m.temas) ...t.lecciones,
    ];
    expect(lecciones, isNotEmpty, reason: 'el mapa necesita lecciones');

    // 5 · Abrir una lección
    final Leccion leccion = await repos.leccion.leccion(lecciones.first.id);
    expect(leccion.bloques, isNotEmpty);
    expect(leccion.titulo, isNotEmpty);

    final Actividad actividad =
        await repos.leccion.empezar(leccion.id);
    expect(actividad.preguntas, isNotEmpty);
    final Pregunta primera = actividad.preguntas.first;
    expect(primera.enunciado, isNotEmpty,
        reason: 'una pregunta sin enunciado no se puede mostrar');

    // 6 · Responder *todas* y cerrar
    //
    // Hay que contestarlas todas: el Reino rechaza cerrar una actividad con
    // preguntas pendientes, y de paso así se ejercita cada tipo que traiga la
    // lección, no solo el primero.
    for (final Pregunta pregunta in actividad.preguntas) {
      final ResultadoRespuesta resultado = await repos.leccion.responder(
        actividad.id,
        preguntaId: pregunta.id,
        tipo: pregunta.tipo,
        respuesta: _respuestaPara(pregunta),
      );
      expect(resultado.preguntaId, pregunta.id,
          reason: 'la corrección debe hablar de la pregunta enviada');
      expect(resultado.explicacion, isNotNull,
          reason: 'el feedback explica, se acierte o se falle');
    }

    final ReciboRecompensas recibo = await repos.leccion.completar(actividad.id);
    expect(recibo.ordenPresentacion, isNotEmpty,
        reason: 'la cola de celebraciones necesita el orden');

    // 7 · El panel refleja lo ocurrido
    final Panel panel = await repos.panel.panel();
    expect(panel.personaje, isNotNull, reason: 'ya creó su personaje');
    expect(panel.accionContinuar, isNotNull,
        reason: 'el panel responde "¿qué hago ahora?"');
    expect(panel.conocimientos, isNotEmpty);

    // 8 · Vestidor y Mercado
    final Pagina<ItemInventario> inventario =
        await repos.inventario.inventario(limite: 60);
    expect(inventario.elementos, isNotEmpty);

    // El kit inicial de la Orden tiene que existir de verdad. Durante mucho
    // tiempo no lo entregaba nadie y el personaje nacía sin nada que ponerse.
    final List<ItemInventario> propios = inventario.elementos
        .where((ItemInventario i) => i.poseido && i.itemUsuarioId != null)
        .toList();
    expect(propios, isNotEmpty, reason: 'la Orden entrega un kit al empezar');

    // Equipar es la prueba de fuego del cuerpo de la petición: el mapa de
    // ranuras viaja envuelto en `equipment`, y mandarlo plano daba 422.
    final Map<RanuraItem, String?> equipo = <RanuraItem, String?>{
      for (final ItemInventario i in propios) i.item.ranura: i.itemUsuarioId,
    };
    final Avatar avatar = await repos.personaje.cambiarEquipo(equipo);
    expect(avatar.equipo, isNotEmpty, reason: 'lo equipado debe volver');

    final Pagina<ItemInventario> despues =
        await repos.inventario.inventario(limite: 60);
    expect(
      despues.elementos.where((ItemInventario i) => i.equipado),
      isNotEmpty,
      reason: 'el Vestidor tiene que ver puesto lo que se acaba de equipar',
    );

    final Tienda tienda = await repos.tienda.tienda();
    expect(tienda.anuncios, isNotEmpty);

    // El permiso de compra se deriva de `owned`, `locked` y `can_afford`, que
    // son los campos que el Reino manda de verdad. Cuando se leía `can_buy`,
    // que no existe, el botón de comprar no se activaba para nadie.
    for (final Anuncio a in tienda.anuncios) {
      if (a.poseido || a.bloqueado || !a.puedePagar) continue;
      expect(a.puedeComprar, isTrue,
          reason: 'se puede pagar, no está bloqueado y no se posee: ${a.item.codigo}');
    }

    // 9 · Racha y misiones
    final Racha racha = await repos.gamificacion.racha();
    expect(racha.mejor, greaterThanOrEqualTo(0));
    final Misiones misiones = await repos.gamificacion.misiones();
    expect(misiones.diarias, isNotEmpty,
        reason: 'el primer día debe haber misiones');
  }, timeout: const Timeout(Duration(minutes: 3)));
}

/// Sustituye el almacén seguro del sistema por uno en memoria.
///
/// Fuera de un teléfono no hay Keychain ni EncryptedSharedPreferences: sin esto
/// la primera lectura de tokens revienta por falta de canal de plataforma y la
/// prueba se saltaría sin haber probado nada.
void _almacenEnMemoria() {
  const MethodChannel canal =
      MethodChannel('plugins.it_nomads.com/flutter_secure_storage');
  final Map<String, String> guardado = <String, String>{};

  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(canal, (MethodCall llamada) async {
    final Map<Object?, Object?> args =
        (llamada.arguments as Map<Object?, Object?>?) ?? <Object?, Object?>{};
    final String clave = (args['key'] ?? '').toString();
    switch (llamada.method) {
      case 'write':
        guardado[clave] = (args['value'] ?? '').toString();
        return null;
      case 'read':
        return guardado[clave];
      case 'readAll':
        return guardado;
      case 'delete':
        guardado.remove(clave);
        return null;
      case 'deleteAll':
        guardado.clear();
        return null;
      case 'containsKey':
        return guardado.containsKey(clave);
      default:
        return null;
    }
  });
}

/// Valor natural con el que responde una pantalla, según el tipo.
///
/// Aquí no se arma el objeto del contrato a propósito: eso es trabajo de
/// [sobreDeRespuesta], y parte de lo que esta prueba comprueba es que esa
/// traducción existe y es la correcta.
Object _respuestaPara(Pregunta pregunta) {
  final List<dynamic> opciones =
      (pregunta.cuerpo['options'] ?? pregunta.cuerpo['items'] ?? <dynamic>[])
          as List<dynamic>;
  List<String> clavesDeOpciones() => <String>[
        for (final dynamic o in opciones)
          if (o is Map && (o['key'] ?? o['id']) != null)
            (o['key'] ?? o['id']).toString(),
      ];

  switch (pregunta.tipo) {
    case TipoPregunta.verdaderoFalso:
      return true;
    case TipoPregunta.completar:
      return <String>['SELECT'];
    case TipoPregunta.ordenar:
      return clavesDeOpciones();
    case TipoPregunta.respuestaCorta:
    case TipoPregunta.casoEstudio:
    case TipoPregunta.ejercicioCodigo:
      return 'Una consulta SELECT recupera las columnas que se le piden de una '
          'tabla, y con WHERE se limita a las filas que cumplen una condición.';
    case TipoPregunta.ejercicioSql:
      return 'SELECT * FROM reinos;';
    case TipoPregunta.relacionar:
      return <String, String>{};
    case TipoPregunta.opcionMultiple:
      final List<String> claves = clavesDeOpciones();
      return claves.isEmpty ? <String>[] : <String>[claves.first];
  }
}
