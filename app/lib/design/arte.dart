import 'package:flutter/material.dart';

import '../datos/modelos.dart';
import 'tokens.dart';

/// Catálogo de arte de Atenea: qué ilustración le corresponde a cada cosa.
///
/// Conviven dos clases de arte, y no son lo mismo.
///
/// Las **ilustraciones de catálogo** —`personajes/` e `items/`— son piezas
/// terminadas: cada una llena su propio lienzo a su escala, y la figura del
/// personaje ya viene vestida. No se pueden apilar. Se usan para las fichas del
/// Vestidor y del Mercado, y para las figuras que todavía no tengan cuerpo
/// desnudo.
///
/// El **arte por capas** —`capas/`— sí se apila: comparte un lienzo maestro de
/// 1024×1024 con cada pieza ya colocada dentro, así que superponer centrado las
/// deja en su sitio sin calcular nada. Lo genera `scripts/vestir.py` y lo trae
/// `scripts/exportar_capas.py`.
///
/// El emparejamiento es por código de ítem. Lo que no tiene ilustración cae al
/// icono de su ranura, que es un marcador honesto: se ve que falta arte, no se
/// finge que existe.
abstract final class Arte {
  static const String _raiz = 'assets/arte';

  /// Las seis figuras que se pueden elegir al crear el personaje.
  static const List<String> personajes = <String>[
    'base_femenino_001',
    'base_femenino_002',
    'base_femenino_003',
    'base_masculino_001',
    'base_masculino_002',
    'base_masculino_003',
  ];

  /// Ruta de la figura completa del personaje.
  static String personaje(String clave) => '$_raiz/personajes/$clave.webp';

  /// Figura por defecto cuando el personaje aún no eligió (o la clave es vieja).
  static String personajePorDefecto(String? clave) {
    if (clave != null && personajes.contains(clave)) return personaje(clave);
    return personaje(personajes.first);
  }

  /// Clave de la figura que le corresponde a un personaje.
  ///
  /// Devuelve la clave (`base_masculino_001`) y no la ruta, porque con la misma
  /// clave se piden tres cosas distintas: la ilustración vestida, el cuerpo
  /// desnudo y la familia de la que sacar las piezas.
  ///
  /// **Si `rostro` ya es una figura, esa es la respuesta.** Desde que la
  /// creación de personaje enseña las seis y deja elegir, la elección viaja en
  /// `face_id` —una columna de 32 caracteres sin valores tasados, así que
  /// `base_femenino_001` cabe sin migración ni cambio de contrato—. Lo que
  /// sigue es solo para los personajes creados antes.
  ///
  /// ## Lo que hacía la derivación, y por qué no valía
  ///
  /// Repartía 34.560 combinaciones ofrecidas entre seis ilustraciones, y lo
  /// hacía mal de dos maneras que nadie podía ver desde la pantalla:
  ///
  ///   - `(variante % 3) + 1` mandaba `face_01` y `face_04` a la **misma**
  ///     figura, así que de cuatro rostros salían tres.
  ///   - la silueta solo se consultaba con trato neutro: quien elegía trato
  ///     masculino o femenino tiraba su silueta sin enterarse.
  ///
  /// Se conserva tal cual, defectos incluidos, porque cambiarla ahora le
  /// cambiaría la cara a quien ya tenga personaje. Eso es peor que ser
  /// imperfecto.
  static String claveDeFigura({
    FormaTrato trato = FormaTrato.neutro,
    TipoCuerpo cuerpo = TipoCuerpo.neutro,
    String rostro = 'face_01',
  }) {
    if (personajes.contains(rostro)) return rostro;

    final int variante = _varianteDe(rostro);
    final bool femenina = switch (trato) {
      FormaTrato.femenino => true,
      FormaTrato.masculino => false,
      // Trato neutro: la silueta esbelta toma la familia femenina y la robusta
      // la masculina; con silueta neutra decide el rostro. Siempre igual para
      // los mismos rasgos.
      FormaTrato.neutro => switch (cuerpo) {
          TipoCuerpo.esbelto => true,
          TipoCuerpo.robusto => false,
          TipoCuerpo.neutro => variante.isEven,
        },
    };
    final String familia = femenina ? 'femenino' : 'masculino';
    return 'base_${familia}_00${(variante % 3) + 1}';
  }

  /// Ruta de la figura completa que le corresponde a un personaje.
  static String figura({
    FormaTrato trato = FormaTrato.neutro,
    TipoCuerpo cuerpo = TipoCuerpo.neutro,
    String rostro = 'face_01',
  }) =>
      personaje(claveDeFigura(trato: trato, cuerpo: cuerpo, rostro: rostro));

  // -------------------------------------------------------------------------
  // Arte por capas
  // -------------------------------------------------------------------------

  /// Figuras que ya tienen cuerpo desnudo, y que por tanto se dibujan apilando.
  ///
  /// Ya son las seis. Se deja como conjunto y no como un `bool` porque el arte
  /// llegó figura a figura y podría volver a pasar: si mañana se añade una
  /// séptima, entra aquí el día que tenga su cuerpo y mientras tanto sigue por
  /// el camino de la ilustración vestida sin que nadie toque el widget.
  ///
  /// Se lleva a mano y a propósito. Flutter no sabe preguntar si un recurso
  /// existe sin intentar cargarlo, así que la alternativa sería descubrirlo por
  /// el `errorBuilder` de cada imagen, ya pintando: para entonces la decisión de
  /// si enseñar las fichas del margen o no ya está tomada, y saldrían las dos
  /// cosas a la vez.
  static const Set<String> conCuerpoDesnudo = <String>{
    'base_masculino_001',
    'base_masculino_002',
    'base_masculino_003',
    'base_femenino_001',
    'base_femenino_002',
    'base_femenino_003',
  };

  /// Cuerpo desnudo de una figura, **sin las manos**.
  ///
  /// El cuerpo se dibuja en tres piezas —este y las dos manos— y no en una,
  /// para que un arma pueda apagar la mano que ocupa. Ver [mano].
  ///
  /// El cuerpo entero sigue en el paquete porque es de donde
  /// `scripts/separar_manos.py` saca las tres piezas, pero ya no lo pinta nadie.
  static String cuerpoSinManos(String clave) =>
      '$_raiz/capas/cuerpos/${clave}_sin_manos.webp';

  /// Una mano suelta de esa figura.
  ///
  /// Existe para poder **quitarla**. Cada pieza empuñada del catálogo trae su
  /// propio puño dibujado —el modelo lo añadió porque no se le dejaba tocar las
  /// manos existentes— y ese puño no tapa del todo a la mano de debajo: asoma
  /// por el borde entre diecinueve y cuarenta y siete píxeles, y se ven dos.
  ///
  /// Moverla no sirve, porque el puño dibujado es más pequeño que la mano. Lo
  /// que sirve es apagar la de debajo.
  ///
  /// `derecha` es desde quien mira, igual que en el taller: la mano que aparece
  /// a la derecha de la imagen es la que sostiene el arma, y la izquierda la
  /// que lleva el escudo.
  static String mano(String clave, {required bool derecha}) =>
      '$_raiz/capas/cuerpos/${clave}_hand_${derecha ? 'right' : 'left'}.webp';

  /// La piel de una mano suelta, para teñirla con el tono del aprendiz.
  ///
  /// Va con [mano] y se apaga con ella. Sin este recorte el arreglo entero no
  /// se vería: [piel] es la silueta completa y se dibuja **por encima** del
  /// cuerpo, así que repintaba el cien por cien de la mano que se acababa de
  /// apagar. Se midió, y era el cien por cien en las seis figuras.
  static String manoPiel(String clave, {required bool derecha}) =>
      '$_raiz/capas/cuerpos/${clave}_piel_hand_${derecha ? 'right' : 'left'}.webp';

  /// Cuerpo desnudo entero. Ya no se pinta: ver [cuerpoSinManos].
  static String cuerpo(String clave) => '$_raiz/capas/cuerpos/$clave.webp';

  /// La piel de esa figura, sola y lista para teñir.
  ///
  /// Es el mismo dibujo con los brillos llevados al blanco, de modo que
  /// multiplicarla por un color —`BlendMode.modulate`— devuelve ese color en la
  /// luz y su sombra correspondiente en la sombra. Se pinta **encima** del
  /// cuerpo, tapando exactamente los píxeles de piel.
  ///
  /// Hace falta normalizarla porque `modulate` solo oscurece, y el tono más
  /// claro del catálogo es más oscuro que la piel dibujada: sobre el recorte
  /// crudo, elegir «marfil» habría oscurecido la piel. La produce
  /// `scripts/separar_piel_y_pelo.py` sin generar arte nuevo.
  static String piel(String clave) => '$_raiz/capas/cuerpos/${clave}_piel.webp';

  /// La piel de esa figura **sin las manos**, que es la que se pinta.
  ///
  /// La entera ya no: tapaba las manos apagadas. Ver [manoPiel].
  static String pielSinManos(String clave) =>
      '$_raiz/capas/cuerpos/${clave}_piel_sin_manos.webp';

  /// El pelo de esa figura, solo y listo para teñir. Ver [piel].
  ///
  /// Este no se parte: se midió y no toca ni un píxel de las manos.
  static String pelo(String clave) => '$_raiz/capas/cuerpos/${clave}_pelo.webp';

  /// Pieza de equipo dentro del juego de capas de su familia.
  ///
  /// El `src` que manda el servidor no dice de qué familia es, y no debe: el
  /// mismo objeto lo llevan las seis figuras. Quien sabe de qué cuerpo se trata
  /// es el cliente, que es quien eligió la figura.
  ///
  /// Y ya trae la extensión: el contrato dice que `src` es «el archivo», así que
  /// ponerla aquí sería decidir en el cliente un formato que decide el servidor.
  static String capaDeEquipo({required String figura, required String src}) =>
      '$_raiz/capas/${_familia(figura)}/$src';

  static String _familia(String figura) =>
      figura.contains('femenino') ? 'femenino' : 'masculino';

  /// Piezas cuyo arte trae su propia mano, ya sacada a capa aparte y teñible.
  ///
  /// Cada pieza empuñada del catálogo venía con un puño dibujado dentro: el
  /// modelo lo añadió porque el estilo le prohibía tocar las manos existentes y
  /// a la vez se le pedía un arma empuñada. En pantalla salían **dos manos**.
  ///
  /// Se probaron dos salidas y las dos se descartaron con medidas, no de oído.
  /// Borrar ese puño deja un hueco que la mano del cuerpo no llega a tapar —es
  /// más pequeña que él, y asomaban entre 434 y 2.204 px—. Taparlo dibujando la
  /// mano encima deja de 114 a 1.071 px de puño naranja alrededor de una mano
  /// oscura. Las dos se vieron componiendo la pila fuera de la aplicación.
  ///
  /// Lo que funciona es lo tercero: ese puño **ya agarra el arma**, porque se
  /// dibujó agarrándola. Lo único que le faltaba era ser del color del aprendiz.
  /// `scripts/quitar_punos.py` lo saca a su propia capa, normalizado para teñir,
  /// y corre la pieza hasta la mano de la figura. El cliente tiñe esa capa y
  /// apaga la mano del cuerpo de ese lado.
  ///
  /// **Por familia y no en una lista sola**: a `arco_bosque_antiguo` masculino
  /// no se le encuentra puño y a `espada_entrenamiento` masculina le quedaría
  /// demasiada muñeca al aire, así que en esas dos la mano del cuerpo tiene que
  /// seguir pintándose. Con una lista común se quedarían mancas.
  ///
  /// La emite el propio guion al terminar; no se escribe a mano.
  static const Map<String, Set<String>> conPunoPropio = <String, Set<String>>{
    'masculino': <String>{
      'arco_bosque_antiguo_weapon',
      'arco_fresno_weapon',
      'baculo_maestria_ia_weapon',
      'baston_aprendiz_weapon',
      'cetro_bigquery_weapon',
      'espada_corta_acero_weapon',
      'espada_del_sql_weapon',
      'espada_entrenamiento_weapon',
      'espada_obsidiana_weapon',
    },
    'femenino': <String>{
      'arco_bosque_antiguo_weapon',
      'arco_fresno_weapon',
      'baculo_maestria_ia_weapon',
      'baston_aprendiz_weapon',
      'cetro_bigquery_weapon',
      'espada_corta_acero_weapon',
      'espada_del_sql_weapon',
      'espada_entrenamiento_weapon',
      'espada_obsidiana_weapon',
    },
  };

  /// ¿Trae esta pieza su propia mano para esta figura?
  ///
  /// `src` es el nombre de archivo tal como lo manda el Reino, con extensión.
  static bool traeSuPuno({required String figura, required String src}) {
    final int punto = src.lastIndexOf('.');
    final String tronco = punto < 0 ? src : src.substring(0, punto);
    return conPunoPropio[_familia(figura)]?.contains(tronco) ?? false;
  }

  /// La mano que trae la pieza, sola y lista para teñir. Ver [conPunoPropio].
  static String punoDeLaPieza({required String figura, required String src}) {
    final int punto = src.lastIndexOf('.');
    final String tronco = punto < 0 ? src : src.substring(0, punto);
    final String extension = punto < 0 ? '.webp' : src.substring(punto);
    return '$_raiz/capas/${_familia(figura)}/${tronco}_puno$extension';
  }

  /// Cómo hay que colocar una pieza de equipo sobre esta figura.
  ///
  /// Devuelve el ajuste neutro para una figura desconocida, que es lo correcto:
  /// una pieza sin ajustar se ve regular, una pieza con un ajuste inventado se
  /// ve peor.
  static AjusteDeFigura ajuste(String figura) =>
      _ajustes[figura] ?? const AjusteDeFigura();

  /// Las medidas de las seis figuras, sacadas de `scripts/medir_figuras.py`.
  ///
  /// **No se editan a mano.** Se regeneran con `python scripts/medir_figuras.py
  /// --dart` cada vez que cambie un cuerpo, y se pegan aquí. Un número tocado a
  /// ojo aquí es un número que ya no describe el arte.
  static const Map<String, AjusteDeFigura> _ajustes = <String, AjusteDeFigura>{
    'base_femenino_001': AjusteDeFigura(
      escalaTorso: 0.8596,
      torsoDx: 66.3,
      diestraDx: -19,
      diestraDy: -3,
      zurdaDx: 14.3,
      zurdaDy: 3.3,
    ),
    'base_femenino_002': AjusteDeFigura(),
    'base_femenino_003': AjusteDeFigura(
      escalaTorso: 0.86,
      torsoDx: 70.5,
      diestraDx: -19,
      diestraDy: -27,
      zurdaDx: 20.9,
      zurdaDy: -20.6,
    ),
    'base_masculino_001': AjusteDeFigura(
      escalaTorso: 0.9032,
      torsoDx: 51.7,
      diestraDx: 4,
      diestraDy: -7,
      zurdaDx: 4.8,
      zurdaDy: 17.6,
    ),
    'base_masculino_002': AjusteDeFigura(),
    'base_masculino_003': AjusteDeFigura(
      escalaTorso: 1.0991,
      torsoDx: -49.7,
      diestraDx: 16,
      diestraDy: -17,
      zurdaDx: -12.1,
      zurdaDy: -10.8,
    ),
  };

  /// Número estable a partir del identificador de rostro (`face_02` -> 2).
  static int _varianteDe(String rostro) {
    final RegExp digitos = RegExp(r'(\d+)');
    final Match? m = digitos.firstMatch(rostro);
    if (m != null) return int.tryParse(m.group(1)!) ?? 0;
    return rostro.codeUnits.fold(0, (int a, int b) => a + b);
  }

  /// Ilustración de un ítem del catálogo, o `null` si todavía no tiene arte.
  static String? item(String? codigo, [String? iconoKey]) {
    final String clave = (codigo?.isNotEmpty ?? false) ? codigo! : (iconoKey ?? '');
    final String? archivo = _porItem[clave];
    return archivo == null ? null : '$_raiz/items/$archivo.webp';
  }

  /// Icono de respaldo por ranura, para lo que aún no tiene ilustración.
  static IconData iconoDeRanura(RanuraItem ranura) => switch (ranura) {
        RanuraItem.cabeza => Icons.sports_motorsports_rounded,
        RanuraItem.cuerpo => Icons.checkroom_rounded,
        RanuraItem.capa => Icons.dry_cleaning_rounded,
        RanuraItem.guantes => Icons.back_hand_rounded,
        RanuraItem.botas => Icons.hiking_rounded,
        RanuraItem.arma => Icons.auto_fix_high_rounded,
        RanuraItem.secundaria => Icons.shield_rounded,
        RanuraItem.accesorio => Icons.diamond_rounded,
        RanuraItem.mascota => Icons.pets_rounded,
        RanuraItem.montura => Icons.emoji_nature_rounded,
      };

  /// Código de ítem del catálogo sembrado -> archivo dentro de `items/`.
  ///
  /// Hay 38 ilustraciones para 46 ítems, así que algunas se comparten entre
  /// piezas de la misma familia. Se anota cuál se repite y por qué.
  ///
  /// Desde que llegaron los guantes, los 46 ítems del catálogo tienen dibujo:
  /// ninguno cae ya al icono de su ranura.
  static const Map<String, String> _porItem = <String, String>{
    // --- Cabeza ---
    'yelmo_veterano': 'cabeza/yelmo',
    'yelmo_guardia': 'cabeza/yelmo', // mismo yelmo, distinto blasón narrativo
    'capucha_viajero': 'cabeza/capucha',
    'sombrero_estrellado': 'cabeza/sombrero',
    'corona_del_maestro': 'cabeza/diadema',
    'corona_laurel_plata': 'cabeza/diadema',
    'corona_fuego_eterno': 'cabeza/diadema',

    // --- Cuerpo ---
    'armadura_placas': 'cuerpo/armadura',
    'cota_escamas_cobre': 'cuerpo/armadura_piel',
    'chaleco_explorador': 'cuerpo/armadura_piel',
    'tunica_iniciacion': 'cuerpo/tunica',
    'sobreveste_vigia': 'cuerpo/tunica_002',
    'tunica_constelaciones': 'cuerpo/tunica_003',
    'jubon_recluta': 'cuerpo/tunica',

    // --- Capa ---
    'capa_lana_gris': 'capa/capa_piel',
    'capa_carmesi': 'capa/capa_002',
    'capa_plumas_nocturnas': 'capa/capa_001',
    'capa_llamas_persistentes': 'capa/capa_002',
    'tpl_capa_estudiante': 'capa/capa_001',
    'tpl_capa_maestro': 'capa/capa_002',

    // --- Guantes ---
    'guantes_cuero': 'guantes/guantes',
    // Prestado: el dibujo es de cuero y los guanteletes son de placas de acero.
    // Sirve mientras no haya uno propio, y se nota que no es el suyo.
    'guanteletes_acero': 'guantes/guantes',

    // --- Botas ---
    'botas_camino': 'botas/botas',
    'botas_reforzadas': 'botas/botas_de_hierro',
    'sandalias_erudito': 'botas/botas_de_piel',
    'botas_caminante': 'botas/botas_de_piel',

    // --- Arma ---
    'espada_entrenamiento': 'arma/daga',
    'espada_corta_acero': 'arma/daga',
    'espada_del_sql': 'arma/espada',
    'espada_obsidiana': 'arma/espada',
    'arco_fresno': 'arma/arco',
    'arco_bosque_antiguo': 'arma/arco',
    'baston_aprendiz': 'arma/baston',
    'baculo_maestria_ia': 'arma/baston',
    'cetro_bigquery': 'arma/orbe',

    // --- Secundaria ---
    'escudo_madera': 'arma/escudo',
    'escudo_roble': 'arma/escudo',
    'escudo_blason_reino': 'arma/escudo',
    'escudo_primer_desafio': 'arma/escudo',
    'escudo_data_engineer': 'arma/escudo',
    'tomo_erudito': 'arma/libro',

    // --- Accesorio ---
    'anteojos_erudito': 'accesorio/anteojos',
    'morral_estudiante': 'accesorio/mochila',
    'pluma_primer_paso': 'arma/pluma',
    'antorcha_constancia': 'arma/linterna',
    'tpl_insignia_perfeccion': 'accesorio/amuleto',
  };

  /// Vista de solo lectura del mapa de ilustraciones.
  ///
  /// La usa la prueba que carga cada archivo: una ruta mal escrita aquí, o una
  /// carpeta sin declarar en `pubspec.yaml`, no da error de compilación y solo
  /// se vería como un hueco en la pantalla del Vestidor.
  static Map<String, String> get ilustracionesPorItem =>
      Map<String, String>.unmodifiable(_porItem);

  /// Ilustraciones que existen y todavía no tiene asignadas ningún ítem.
  ///
  /// Se dejan listadas para que se note que están disponibles cuando el
  /// catálogo crezca: bolso, cinturón, poción, pergamino y los seis peinados.
  static const List<String> sinAsignar = <String>[
    'accesorio/bolso',
    'accesorio/cinturon',
    'accesorio/pocion',
    'arma/pergamino',
    'cabello/cabello_femenino_001',
    'cabello/cabello_femenino_002',
    'cabello/cabello_femenino_003',
    'cabello/cabello_hombre_001',
    'cabello/cabello_hombre_002',
    'cabello/cabello_hombre_003',
  ];
}

/// Dibuja la ilustración de un ítem, o su icono de ranura si aún no tiene arte.
class ImagenItem extends StatelessWidget {
  const ImagenItem({
    required this.codigo,
    required this.ranura,
    super.key,
    this.iconoKey,
    this.tamano = 48,
    this.color,
    this.apagado = false,
  });

  /// Código del ítem del catálogo (`espada_del_sql`).
  final String codigo;

  final RanuraItem ranura;
  final String? iconoKey;
  final double tamano;

  /// Color del icono de respaldo. La ilustración nunca se tiñe.
  final Color? color;

  /// Bloqueado o no disponible: se muestra atenuado.
  final bool apagado;

  @override
  Widget build(BuildContext context) {
    final String? ruta = Arte.item(codigo, iconoKey);
    final Color colorIcono = color ?? context.paleta.textoSecundario;

    if (ruta == null) {
      return Icon(
        Arte.iconoDeRanura(ranura),
        size: tamano * 0.8,
        color: apagado ? colorIcono.withValues(alpha: 0.35) : colorIcono,
      );
    }

    final Widget imagen = Image.asset(
      ruta,
      width: tamano,
      height: tamano,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      // Si el archivo faltara, el icono de la ranura sigue siendo una respuesta
      // válida: nunca una caja rota.
      errorBuilder: (BuildContext context, Object error, StackTrace? pila) => Icon(
        Arte.iconoDeRanura(ranura),
        size: tamano * 0.8,
        color: colorIcono,
      ),
    );

    if (!apagado) return imagen;
    return Opacity(
      opacity: 0.4,
      child: ColorFiltered(
        colorFilter: const ColorFilter.matrix(<double>[
          0.2126, 0.7152, 0.0722, 0, 0, //
          0.2126, 0.7152, 0.0722, 0, 0, //
          0.2126, 0.7152, 0.0722, 0, 0, //
          0, 0, 0, 1, 0, //
        ]),
        child: imagen,
      ),
    );
  }
}

/// Dibuja la figura completa del personaje.
class ImagenPersonaje extends StatelessWidget {
  const ImagenPersonaje({
    required this.clave,
    super.key,
    this.alto = 220,
    this.alineacion = Alignment.topCenter,
  });

  /// Clave de la figura (`base_femenino_001`).
  final String? clave;
  final double alto;
  final Alignment alineacion;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      Arte.personajePorDefecto(clave),
      height: alto,
      fit: BoxFit.contain,
      alignment: alineacion,
      filterQuality: FilterQuality.medium,
      errorBuilder: (BuildContext context, Object error, StackTrace? pila) => Icon(
        Icons.person_rounded,
        size: alto * 0.6,
        color: context.paleta.textoSecundario,
      ),
    );
  }
}

/// Cómo se coloca una pieza de equipo sobre una figura que no es la canónica.
///
/// Las 46 piezas se generaron **por familia**, editando la ilustración de una
/// figura de cada una. Sobre esa figura encajan al milímetro; sobre las otras
/// dos, no. Y no por poco: el torso varía hasta 28 px por lado, y la mano
/// cambia de altura hasta 48. Como cada arma lleva dibujado su propio puño
/// agarrándola, esos 48 px son la distancia entre ese puño y la mano del
/// cuerpo, y se acaban viendo **las dos manos**.
///
/// Los números salen de medir los seis cuerpos, no de ajustar a ojo: los
/// calcula `scripts/medir_figuras.py` y se pegan en `Arte._ajustes`.
///
/// Lo que esto **no** arregla, para que no se espere de más: una pieza dibujada
/// para otro cuerpo sigue siendo una pieza dibujada para otro cuerpo. Se coloca
/// y se ajusta de talla; no cambia de postura ni de perspectiva. El arreglo
/// completo es generar las 46 piezas para las seis figuras en vez de para dos.
class AjusteDeFigura {
  const AjusteDeFigura({
    this.escalaTorso = 1,
    this.torsoDx = 0,
    this.diestraDx = 0,
    this.diestraDy = 0,
    this.zurdaDx = 0,
    this.zurdaDy = 0,
  });

  /// Cuánto ensanchar una pieza que se ciñe al torso.
  final double escalaTorso;

  /// Y cuánto recolocarla después, porque escalar mueve el centro.
  final double torsoDx;

  /// Cuánto mover una pieza según en qué mano vaya.
  ///
  /// **La diestra no apunta al centro de la mano, sino un poco por encima.** Es
  /// la que sostiene el arma, y cuando la pieza trae su propio puño la mano del
  /// cuerpo se apaga: entonces lo que se ve no es si el arma está centrada sino
  /// si queda muñeca al aire. Apuntando al centroide quedaban 1.812 px
  /// destapados en `base_masculino_001`; buscando el desplazamiento que menos
  /// muñeca deja —a 3-9 px del centroide— bajan a 236. La zurda sí va al
  /// centroide, porque su mano no se apaga nunca: la tapa el escudo.
  ///
  /// **Una por mano, y no una para las dos.** Las dos manos no se desplazan
  /// juntas de una figura a otra: en `base_femenino_003` la derecha está 22 px
  /// a la izquierda de la canónica y la izquierda 21 px a la **derecha**. Con un
  /// solo par de números, a un escudo se le aplicaba el de la espada y se iba
  /// 43 px en la dirección contraria: flotaba separado del cuerpo en vez de
  /// apoyarse en el brazo. Se ve en `arte/diagnostico/ajustes.png`.
  ///
  /// «Diestra» y «zurda» son desde quien mira, igual que en el taller: la
  /// diestra es la mano que aparece a la derecha de la imagen, la que lleva el
  /// arma.
  final double diestraDx;
  final double diestraDy;
  final double zurdaDx;
  final double zurdaDy;

  /// ¿Esta figura necesita que se le ajuste algo?
  ///
  /// Las dos canónicas no, y saberlo evita envolver sus capas en una
  /// transformación que no hace nada.
  bool get esNeutro =>
      escalaTorso == 1 &&
      torsoDx == 0 &&
      diestraDx == 0 &&
      diestraDy == 0 &&
      zurdaDx == 0 &&
      zurdaDy == 0;
}

/// Qué transformación le toca a cada capa de la pila de dibujado.
///
/// La distinción no es decorativa: una túnica se **ciñe** al cuerpo y hay que
/// darle la talla, mientras que una espada se **sostiene** y solo hay que
/// llevarla a donde está la mano. Estirar una espada la engorda; mover una
/// túnica la descoloca.
enum TrazoDeCapa {
  /// Se ciñe al torso: túnica, capa, accesorio de cuerpo.
  talla,

  /// Se sostiene con la mano: arma, secundaria, guantes.
  mano,

  /// Ni una cosa ni otra: cara, pelo, cabeza, botas, montura, mascota. Estas
  /// piezas van sobre partes que el ajuste de torso no describe, y moverlas con
  /// la mano las mandaría a cualquier sitio.
  ninguno;

  /// El trazo que le corresponde al nombre de capa que manda el Reino.
  static TrazoDeCapa de(String capa) => switch (capa) {
        'outfit' || 'cape_back' || 'cape_front' || 'accessory_body' => talla,
        'weapon' || 'offhand' || 'gloves' => mano,
        _ => ninguno,
      };
}
