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

  /// Cuerpo desnudo de una figura: el fondo de la pila de dibujado.
  static String cuerpo(String clave) => '$_raiz/capas/cuerpos/$clave.webp';

  /// Pieza de equipo dentro del juego de capas de su familia.
  ///
  /// El `src` que manda el servidor no dice de qué familia es, y no debe: el
  /// mismo objeto lo llevan las seis figuras. Quien sabe de qué cuerpo se trata
  /// es el cliente, que es quien eligió la figura.
  ///
  /// Y ya trae la extensión: el contrato dice que `src` es «el archivo», así que
  /// ponerla aquí sería decidir en el cliente un formato que decide el servidor.
  static String capaDeEquipo({required String figura, required String src}) {
    final String familia = figura.contains('femenino') ? 'femenino' : 'masculino';
    return '$_raiz/capas/$familia/$src';
  }

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
