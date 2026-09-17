/// Render del avatar por capas (§6.4 del documento de experiencia).
///
/// El servidor manda siempre el manifiesto de capas ya ordenado por z; el
/// cliente nunca lo recompone.
///
/// ## Dos formas de dibujar, y por qué conviven
///
/// **Apilando**, que es lo que se quiere: un cuerpo desnudo de fondo y encima
/// cada pieza en su propia imagen. Las capas comparten el lienzo maestro de
/// 1024×1024 con la pieza ya colocada dentro, así que superponerlas centradas y
/// al mismo alto las deja en su sitio sin calcular ni un desplazamiento. Eso no
/// es casualidad: `scripts/vestir.py` las genera pintando sobre el cuerpo, y una
/// pieza que nace ahí nunca se movió.
///
/// **Con fichas al margen**, que es lo que había: una ilustración completa del
/// personaje —ya vestida de fábrica— y el equipo alrededor, en los dos huecos
/// laterales. Era la única salida cuando cada pieza era una ficha de catálogo
/// recortada a su propio encuadre: superponerlas daba un collage.
///
/// Se elige por figura, no globalmente, porque el arte por capas llega figura a
/// figura: `Arte.conCuerpoDesnudo` dice cuáles ya lo tienen. Y dentro del modo
/// apilado se elige otra vez por pieza: la que todavía no tiene capa sigue
/// saliendo como ficha al margen, en vez de desaparecer del avatar. Según llega
/// arte, las fichas se van solas.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/arte.dart';
import '../../entrada/widgets/catalogo_avatar.dart';
import '../../../design/tokens.dart';

/// Compone una vista previa: las capas actuales con las de [item] puestas en
/// su ranura.
List<CapaAvatar> capasConItem(List<CapaAvatar> base, Item item) {
  final List<CapaAvatar> compuestas = <CapaAvatar>[
    for (final CapaAvatar c in base)
      if (c.ranura != item.ranura) c,
    if (item.capas.isNotEmpty)
      ...item.capas
    else
      // El ítem no trae capas resueltas (el catálogo solo guarda su manifiesto
      // crudo), así que se fabrica la mínima que la vista previa necesita: de
      // qué ranura es y qué ilustración pintar.
      CapaAvatar(
        clave: item.ranura.name,
        ranura: item.ranura,
        codigoItem: item.codigo.isEmpty ? null : item.codigo,
        itemId: item.id,
        z: 50,
      ),
  ]..sort((CapaAvatar a, CapaAvatar b) => a.z.compareTo(b.z));
  return compuestas;
}

/// Avatar 2D frontal compuesto por capas.
class AvatarCapas extends StatelessWidget {
  const AvatarCapas({
    required this.capas,
    super.key,
    this.rasgos,
    this.tamano = 220,
    this.resplandor = true,
    this.nombre,
  });

  /// Manifiesto de capas tal como lo envía el Reino.
  final List<CapaAvatar> capas;

  /// Rasgos gratuitos (piel, cabello, silueta).
  final RasgosAvatar? rasgos;

  /// Lado del lienzo cuadrado, en dp.
  final double tamano;

  /// Halo de luz detrás del personaje.
  final bool resplandor;

  /// Nombre del personaje, para el lector de pantalla.
  final String? nombre;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final RasgosAvatar r = rasgos ?? const RasgosAvatar();

    final String clave = Arte.claveDeFigura(
      trato: r.formaTrato,
      cuerpo: r.tipoCuerpo,
      rostro: r.rostro,
    );
    final bool apilando = Arte.conCuerpoDesnudo.contains(clave);

    final Map<RanuraItem, Color> equipo = <RanuraItem, Color>{};
    final Map<RanuraItem, String> piezas = <RanuraItem, String>{};
    final Set<RanuraItem> conCapa = <RanuraItem>{};
    for (final CapaAvatar capa in capas) {
      final RanuraItem? ranura = capa.ranura;
      if (ranura == null) continue;
      equipo[ranura] = _colorDeTinte(capa.tinte) ?? _colorPorRanura(ranura, p);
      // Una capa aporta varias capas (espalda y broche) y todas traen el mismo
      // código: el mapa se queda con una y ya está.
      final String? codigo = capa.codigoItem;
      if (codigo != null && codigo.isNotEmpty) piezas[ranura] = codigo;
      if (capa.assetKey.isNotEmpty) conCapa.add(ranura);
    }

    // Al margen solo lo que no se puede pintar encima. Sin esto, una pieza sin
    // arte por capas desaparecería del avatar al estrenar el modo apilado: el
    // aprendiz habría pagado oro por algo que dejó de verse.
    final Map<RanuraItem, String> alMargen = apilando
        ? <RanuraItem, String>{
            for (final MapEntry<RanuraItem, String> e in piezas.entries)
              if (!conCapa.contains(e.key)) e.key: e.value,
          }
        : piezas;

    // El cuerpo no es el fondo de la pila: es una capa más, `body_base`, y hay
    // cuatro por debajo suyo. Una capa prendida a los hombros cuelga POR DETRÁS
    // del aprendiz, y pintarla encima de todo la convertía en un babero.
    final List<CapaAvatar> detras = <CapaAvatar>[
      for (final CapaAvatar c in capas)
        if (c.assetKey.isNotEmpty && c.z < zDelCuerpo) c,
    ];
    // Y de lo que va por delante, los guantes van aparte porque van sobre la
    // mano: se pintan después de ella, no antes. El resto —el arma incluida— va
    // debajo, que es lo que hace que la mano parezca agarrarla.
    final List<CapaAvatar> delante = <CapaAvatar>[
      for (final CapaAvatar c in capas)
        if (c.assetKey.isNotEmpty && c.z >= zDelCuerpo && c.ranura != RanuraItem.guantes) c,
    ];
    final List<CapaAvatar> sobreLasManos = <CapaAvatar>[
      for (final CapaAvatar c in capas)
        if (c.assetKey.isNotEmpty && c.z >= zDelCuerpo && c.ranura == RanuraItem.guantes) c,
    ];

    final List<String> puestos = <String>[
      for (final RanuraItem ranura in ranurasDelVestidorInterno)
        if (equipo.containsKey(ranura)) _nombreRanura(ranura).toLowerCase(),
    ];

    return Semantics(
      label: nombre == null
          ? 'Avatar del personaje'
          : 'Avatar de $nombre',
      value: puestos.isEmpty
          ? 'Sin equipamiento'
          : 'Lleva ${puestos.join(', ')}',
      excludeSemantics: true,
      child: SizedBox(
        width: tamano,
        height: tamano,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            // El halo se pinta aparte: la figura es una ilustración, no un
            // dibujo vectorial, y el resplandor debe quedar por detrás.
            if (resplandor)
              CustomPaint(
                size: Size.square(tamano),
                painter: _PintorAvatar(
                  paleta: p,
                  equipo: equipo,
                  piel: CatalogoAvatar.piel(r.tonoPiel),
                  cabello: CatalogoAvatar.cabello(r.colorCabello),
                  esbelto: r.tipoCuerpo == TipoCuerpo.esbelto,
                  robusto: r.tipoCuerpo == TipoCuerpo.robusto,
                  resplandor: true,
                  soloFondo: true,
                ),
              ),
            // Lo que va por detrás del cuerpo: la espalda de una capa, el
            // pelo de atrás, un aura. Cuatro de las diecinueve capas de la pila
            // caen ahí.
            if (apilando)
              for (final CapaAvatar capa in detras) _Capa(capa: capa, figura: clave, lado: tamano),
            Image.asset(
              apilando ? Arte.cuerpoSinManos(clave) : Arte.personaje(clave),
              height: tamano,
              fit: BoxFit.contain,
              filterQuality: FilterQuality.medium,
              // Si el arte faltara, el dibujo vectorial sigue siendo una figura
              // válida: la pantalla nunca queda vacía.
              errorBuilder: (BuildContext context, Object error, StackTrace? pila) =>
                  CustomPaint(
                size: Size.square(tamano),
                painter: _PintorAvatar(
                  paleta: p,
                  equipo: equipo,
                  piel: CatalogoAvatar.piel(r.tonoPiel),
                  cabello: CatalogoAvatar.cabello(r.colorCabello),
                  esbelto: r.tipoCuerpo == TipoCuerpo.esbelto,
                  robusto: r.tipoCuerpo == TipoCuerpo.robusto,
                  resplandor: resplandor,
                ),
              ),
            ),
            // La piel y el pelo del aprendiz, teñidos con lo que eligió.
            //
            // Van pegados al cuerpo y debajo de todo el equipo, que es su sitio
            // en la pila: una armadura tapa la piel, no al revés. Son el mismo
            // dibujo del cuerpo con los brillos llevados al blanco, así que
            // multiplicarlos por el color devuelve ese color donde da la luz y
            // su sombra donde hay sombra.
            //
            // Hasta que existieron, la pantalla de creación ofrecía seis tonos
            // de piel y diez colores de pelo que no cambiaban nada: en el arte
            // había dos tonos de piel, uno por familia, y seis colores de pelo
            // soldados cada uno a su figura.
            if (apilando) ...<Widget>[
              _Tinte(
                ruta: Arte.pielSinManos(clave),
                color: CatalogoAvatar.piel(r.tonoPiel),
                lado: tamano,
              ),
              _Tinte(ruta: Arte.pelo(clave), color: CatalogoAvatar.cabello(r.colorCabello), lado: tamano),
            ],
            // Y lo que va por delante, en el orden que manda el Reino.
            if (apilando)
              for (final CapaAvatar capa in delante) _Capa(capa: capa, figura: clave, lado: tamano),
            // Las manos, cada una con su piel teñida, y **sobre el arma**.
            //
            // Son ellas las que agarran. Cada pieza empuñada traía su propio
            // puño dibujado, porque al generarla se le prohibía al modelo tocar
            // las manos existentes y a la vez se le pedía un arma empuñada; en
            // pantalla salían dos manos, y así lo encontró el primer aprendiz
            // que equipó una espada.
            //
            // `scripts/quitar_punos.py` le quitó ese puño a las piezas y las
            // corrió para que la empuñadura caiga donde está esta mano. Por eso
            // el orden importa: debajo del arma se vería el puño de la pieza
            // —naranja, y sin teñir, sobre cualquiera de los seis tonos de
            // piel—; encima, agarra la del aprendiz, que sí se tiñe.
            //
            // Dibujarlas siempre y no apagar ninguna no es pereza: apagarla deja
            // el antebrazo cortado en seco, y se vio componiendo la pila fuera
            // de la aplicación.
            if (apilando)
              for (final bool derecha in <bool>[true, false]) ...<Widget>[
                _CapaDelCuerpo(ruta: Arte.mano(clave, derecha: derecha), lado: tamano),
                _Tinte(
                  ruta: Arte.manoPiel(clave, derecha: derecha),
                  color: CatalogoAvatar.piel(r.tonoPiel),
                  lado: tamano,
                ),
              ],
            // Y los guantes al final, que van sobre la mano. Un guante debajo de
            // ella es un guante que no se ve.
            if (apilando)
              for (final CapaAvatar capa in sobreLasManos)
                _Capa(capa: capa, figura: clave, lado: tamano),
            // Las fichas del equipo, en los dos márgenes que la figura deja
            // libres. Es lo único que se podía hacer mientras cada pieza fuera
            // una ficha de catálogo con su propio encuadre, y sigue siendo la
            // salida para lo que aún no tiene capa: alrededor, el oro del
            // Mercado compra algo que se ve.
            if (alMargen.isNotEmpty)
              Positioned.fill(
                child: _FichasDelEquipo(piezas: alMargen, lado: tamano * 0.19),
              ),
          ],
        ),
      ),
    );
  }
}

/// Una región del cuerpo —la piel, el pelo— teñida con el color elegido.
///
/// Si el recurso no existe, no se pinta nada y el cuerpo se ve con el color con
/// el que se dibujó. Es la degradación correcta: una figura sin capas teñibles
/// sale como salía antes, no rota.
class _Tinte extends StatelessWidget {
  const _Tinte({required this.ruta, required this.color, required this.lado});

  final String ruta;
  final Color color;
  final double lado;

  @override
  Widget build(BuildContext context) => Image.asset(
        ruta,
        height: lado,
        fit: BoxFit.contain,
        filterQuality: FilterQuality.medium,
        color: color,
        colorBlendMode: BlendMode.modulate,
        errorBuilder: (BuildContext context, Object error, StackTrace? pila) =>
            const SizedBox.shrink(),
      );
}

/// Una capa del manifiesto, pintada sobre el lienzo maestro.
///
/// Sin `x`, `y`, `ancho` ni `alto`: cada capa ya viene dibujada dentro del
/// lienzo de 1024×1024, con su sitio hecho y transparencia alrededor. Centradas
/// y al mismo alto, encajan solas. Los desplazamientos del manifiesto son para
/// el día que una pieza se recorte a su caja para ahorrar bytes; hoy ninguna lo
/// está, y aplicarlos ahora los aplicaría dos veces.
class _Capa extends StatelessWidget {
  const _Capa({required this.capa, required this.figura, required this.lado});

  final CapaAvatar capa;
  final String figura;
  final double lado;

  /// Coloca la pieza sobre esta figura si no es la canónica de su familia.
  ///
  /// Las piezas se dibujaron sobre una figura por familia, así que sobre las
  /// otras dos van desplazadas y de otra talla. Aquí se corrige con las medidas
  /// de `Arte.ajuste`, y solo donde tiene sentido: la ropa se ciñe al torso y
  /// pide talla; el arma se sostiene y pide sitio. Ver [TrazoDeCapa].
  ///
  /// Las dos figuras canónicas salen por el camino corto, sin envolver nada.
  Widget _colocada(Widget imagen) {
    final AjusteDeFigura a = Arte.ajuste(figura);
    if (a.esNeutro) return imagen;

    // Las medidas están tomadas sobre el lienzo maestro de 1024, y aquí la capa
    // se pinta a `lado`. Sin este factor, en una ficha pequeña el arma saltaría
    // media pantalla.
    final double k = lado / 1024;

    return switch (TrazoDeCapa.de(capa.clave)) {
      TrazoDeCapa.talla => Transform(
          alignment: Alignment.topLeft,
          transform: Matrix4.identity()
            ..translateByDouble(a.torsoDx * k, 0, 0, 1)
            ..scaleByDouble(a.escalaTorso, 1, 1, 1),
          child: imagen,
        ),
      TrazoDeCapa.mano => Transform.translate(
          offset: Offset(a.manoDx * k, a.manoDy * k),
          child: imagen,
        ),
      TrazoDeCapa.ninguno => imagen,
    };
  }

  @override
  Widget build(BuildContext context) {
    final Color? tinte = _colorDeTinte(capa.tinte);
    return _colocada(Image.asset(
      Arte.capaDeEquipo(figura: figura, src: capa.assetKey),
      height: lado,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      // `modulate` multiplica, así que tiñe conservando el sombreado y el
      // contorno. Es lo que necesitan los cosméticos de conocimiento: un solo
      // dibujo y un color por disciplina.
      color: tinte,
      colorBlendMode: tinte == null ? null : BlendMode.modulate,
      // Una capa que falta no rompe el avatar ni deja un hueco negro:
      // sencillamente no se pinta, y su ficha al margen sigue diciendo que la
      // pieza está puesta.
      errorBuilder: (BuildContext context, Object error, StackTrace? pila) =>
          const SizedBox.shrink(),
    ));
  }
}

/// Las piezas equipadas, repartidas en las dos columnas laterales.
class _FichasDelEquipo extends StatelessWidget {
  const _FichasDelEquipo({required this.piezas, required this.lado});

  final Map<RanuraItem, String> piezas;
  final double lado;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final List<RanuraItem> puestas = <RanuraItem>[
      for (final RanuraItem ranura in ranurasDelVestidorInterno)
        if (piezas.containsKey(ranura)) ranura,
    ];
    // Se reparten por mitades conservando el orden del Vestidor, para que una
    // pieza no salte de lado al equipar otra.
    final int corte = (puestas.length + 1) ~/ 2;

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        _columna(p, puestas.take(corte)),
        _columna(p, puestas.skip(corte)),
      ],
    );
  }

  Widget _columna(AteneaPalette p, Iterable<RanuraItem> ranuras) => Column(
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (final RanuraItem ranura in ranuras)
            Padding(
              padding: EdgeInsets.symmetric(vertical: lado * 0.08),
              child: Tooltip(
                message: _nombreRanura(ranura),
                child: ImagenItem(
                  codigo: piezas[ranura]!,
                  ranura: ranura,
                  tamano: lado,
                  color: _colorPorRanura(ranura, p),
                ),
              ),
            ),
        ],
      );
}

/// Marco del Vestidor: pedestal, halo y avatar centrado.
class RetratoAvatar extends StatelessWidget {
  const RetratoAvatar({
    required this.capas,
    super.key,
    this.rasgos,
    this.nombre,
    this.subtitulo,
    this.tamano = 220,
    this.cargando = false,
  });

  final List<CapaAvatar> capas;
  final RasgosAvatar? rasgos;
  final String? nombre;
  final String? subtitulo;
  final double tamano;
  final bool cargando;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    if (cargando) {
      return Center(
        child: SizedBox(
          width: tamano,
          height: tamano,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: p.borde.withValues(alpha: 0.45),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Icon(
                Icons.person_rounded,
                size: tamano * 0.42,
                color: p.superficie,
              ),
            ),
          ),
        ),
      );
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        AvatarCapas(
          capas: capas,
          rasgos: rasgos,
          tamano: tamano,
          nombre: nombre,
        ),
        if (nombre != null) ...<Widget>[
          const SizedBox(height: Espacio.xs),
          Text(
            nombre!,
            textAlign: TextAlign.center,
            style: context.textos.displaySmall,
          ),
        ],
        if (subtitulo != null)
          Text(
            subtitulo!,
            textAlign: TextAlign.center,
            style: context.textos.bodyMedium?.copyWith(
              color: p.textoSecundario,
            ),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Colores derivados
// ---------------------------------------------------------------------------

/// Dónde entra el cuerpo en la pila de dibujado (06c §2.3).
///
/// El cuerpo no es el fondo: es la capa `body_base`, y la pila tiene cuatro por
/// debajo —la montura, la espalda de la capa, el aura y el pelo de detrás—. Una
/// capa prendida a los hombros cuelga por detrás del aprendiz, así que pintarla
/// encima de todo la convertiría en un babero.
///
/// Es el único número de la pila del servidor que el cliente necesita saber, y
/// lo necesita porque el cuerpo llega por otro camino: no viene en `layers[]`,
/// se elige aquí a partir de los rasgos. El día que el servidor mande también
/// `body_base` con su `src`, esto sobra y las capas se pintan en fila.
const int zDelCuerpo = 40;

/// Las ranuras que el dibujo sabe representar.
const List<RanuraItem> ranurasDelVestidorInterno = <RanuraItem>[
  RanuraItem.cabeza,
  RanuraItem.cuerpo,
  RanuraItem.capa,
  RanuraItem.arma,
  RanuraItem.secundaria,
  RanuraItem.accesorio,
  RanuraItem.guantes,
  RanuraItem.botas,
];

String _nombreRanura(RanuraItem ranura) =>
    ranura == RanuraItem.secundaria ? 'Escudo' : ranura.etiqueta;

/// Lee un tinte `#RRGGBB` del manifiesto.
Color? _colorDeTinte(String? tinte) {
  if (tinte == null) return null;
  final String limpio = tinte.replaceAll('#', '').trim();
  if (limpio.length != 6 && limpio.length != 8) return null;
  final int? valor = int.tryParse(limpio, radix: 16);
  if (valor == null) return null;
  return Color(limpio.length == 6 ? 0xFF000000 | valor : valor);
}

/// Color semántico de reserva para cada ranura.
Color _colorPorRanura(RanuraItem ranura, AteneaPalette p) => switch (ranura) {
      RanuraItem.cabeza => p.arcano,
      RanuraItem.cuerpo => p.info,
      RanuraItem.capa => p.brasa,
      RanuraItem.arma => p.oro,
      RanuraItem.secundaria => p.dominio,
      RanuraItem.accesorio => p.exito,
      RanuraItem.guantes => p.textoSecundario,
      RanuraItem.botas => p.textoSecundario,
      RanuraItem.mascota => p.exito,
      RanuraItem.montura => p.advertencia,
    };




// ---------------------------------------------------------------------------
// Pintor
// ---------------------------------------------------------------------------

class _PintorAvatar extends CustomPainter {
  const _PintorAvatar({
    required this.paleta,
    required this.equipo,
    required this.piel,
    required this.cabello,
    required this.esbelto,
    required this.robusto,
    required this.resplandor,
    this.soloFondo = false,
  });

  final AteneaPalette paleta;
  final Map<RanuraItem, Color> equipo;
  final Color piel;
  final Color cabello;
  final bool esbelto;
  final bool robusto;
  final bool resplandor;

  /// Pinta solo el halo y el pedestal, sin la figura.
  ///
  /// Es lo que se usa detrás de la ilustración del personaje: el escenario sí,
  /// el muñeco vectorial no.
  final bool soloFondo;

  @override
  void paint(Canvas lienzo, Size medida) {
    final double s = medida.shortestSide;
    final double dx = (medida.width - s) / 2;
    lienzo.translate(dx, 0);

    final Paint relleno = Paint()..style = PaintingStyle.fill;

    // Halo de luz y pedestal.
    if (resplandor) {
      relleno.shader = RadialGradient(
        colors: <Color>[
          paleta.arcano.withValues(alpha: 0.28),
          paleta.arcano.withValues(alpha: 0.06),
          Colors.transparent,
        ],
        stops: const <double>[0, 0.55, 1],
      ).createShader(Rect.fromLTWH(0, 0, s, s));
      lienzo.drawCircle(Offset(s * 0.5, s * 0.5), s * 0.5, relleno);
      relleno.shader = null;
    }

    relleno.color = paleta.borde.withValues(alpha: 0.7);
    lienzo.drawOval(
      Rect.fromCenter(
        center: Offset(s * 0.5, s * 0.935),
        width: s * 0.44,
        height: s * 0.06,
      ),
      relleno,
    );

    if (soloFondo) return;

    final double ancho = esbelto ? 0.135 : (robusto ? 0.185 : 0.16);
    final Color cuerpo = equipo[RanuraItem.cuerpo] ?? paleta.superficieElevada;
    final Color botas = equipo[RanuraItem.botas] ?? paleta.borde;
    final Color guantes = equipo[RanuraItem.guantes] ?? piel;

    // Capa, detrás de todo el cuerpo.
    final Color? capa = equipo[RanuraItem.capa];
    if (capa != null) {
      final Path manto = Path()
        ..moveTo(s * (0.5 - ancho - 0.02), s * 0.46)
        ..lineTo(s * (0.5 - ancho - 0.13), s * 0.90)
        ..quadraticBezierTo(s * 0.5, s * 0.96, s * (0.5 + ancho + 0.13), s * 0.90)
        ..lineTo(s * (0.5 + ancho + 0.02), s * 0.46)
        ..close();
      relleno.color = capa.withValues(alpha: 0.92);
      lienzo.drawPath(manto, relleno);
      relleno.color = Color.lerp(capa, paleta.fondo, 0.35) ?? capa;
      lienzo.drawPath(
        Path()
          ..moveTo(s * 0.5, s * 0.48)
          ..lineTo(s * 0.5, s * 0.94)
          ..lineTo(s * (0.5 + ancho + 0.13), s * 0.90)
          ..lineTo(s * (0.5 + ancho + 0.02), s * 0.46)
          ..close(),
        relleno,
      );
    }

    // Piernas y botas.
    relleno.color = piel;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            s * (0.5 + lado * ancho * 0.62 - 0.035),
            s * 0.74,
            s * 0.07,
            s * 0.16,
          ),
          Radius.circular(s * 0.03),
        ),
        relleno,
      );
    }
    relleno.color = botas;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            s * (0.5 + lado * ancho * 0.62 - 0.042),
            s * 0.855,
            s * 0.084,
            s * 0.055,
          ),
          Radius.circular(s * 0.02),
        ),
        relleno,
      );
    }

    // Brazos.
    relleno.color = Color.lerp(cuerpo, paleta.fondo, 0.18) ?? cuerpo;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(
            s * (0.5 + lado * (ancho + 0.055) - 0.028),
            s * 0.50,
            s * 0.056,
            s * 0.21,
          ),
          Radius.circular(s * 0.028),
        ),
        relleno,
      );
    }
    relleno.color = guantes;
    for (final double lado in <double>[-1, 1]) {
      lienzo.drawCircle(
        Offset(s * (0.5 + lado * (ancho + 0.055)), s * 0.715),
        s * 0.032,
        relleno,
      );
    }

    // Torso.
    relleno.color = cuerpo;
    lienzo.drawRRect(
      RRect.fromRectAndCorners(
        Rect.fromLTWH(s * (0.5 - ancho), s * 0.465, s * ancho * 2, s * 0.30),
        topLeft: Radius.circular(s * 0.08),
        topRight: Radius.circular(s * 0.08),
        bottomLeft: Radius.circular(s * 0.035),
        bottomRight: Radius.circular(s * 0.035),
      ),
      relleno,
    );

    // Cinturón.
    relleno.color = paleta.borde;
    lienzo.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(s * (0.5 - ancho), s * 0.705, s * ancho * 2, s * 0.028),
        Radius.circular(s * 0.012),
      ),
      relleno,
    );

    // Hombreras cuando hay armadura equipada.
    if (equipo.containsKey(RanuraItem.cuerpo)) {
      relleno.color = Color.lerp(cuerpo, paleta.textoPrimario, 0.22) ?? cuerpo;
      for (final double lado in <double>[-1, 1]) {
        lienzo.drawCircle(
          Offset(s * (0.5 + lado * (ancho + 0.01)), s * 0.50),
          s * 0.052,
          relleno,
        );
      }
    }

    // Accesorio en el pecho.
    final Color? accesorio = equipo[RanuraItem.accesorio];
    if (accesorio != null) {
      final Path gema = Path()
        ..moveTo(s * 0.5, s * 0.545)
        ..lineTo(s * 0.528, s * 0.578)
        ..lineTo(s * 0.5, s * 0.612)
        ..lineTo(s * 0.472, s * 0.578)
        ..close();
      relleno.color = accesorio;
      lienzo.drawPath(gema, relleno);
    }

    // Cuello y cabeza.
    relleno.color = Color.lerp(piel, paleta.fondo, 0.2) ?? piel;
    lienzo.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(s * 0.465, s * 0.425, s * 0.07, s * 0.06),
        Radius.circular(s * 0.02),
      ),
      relleno,
    );

    const double centroCabezaY = 0.345;
    final double radioCabeza = s * 0.105;
    relleno.color = piel;
    lienzo.drawCircle(
      Offset(s * 0.5, s * centroCabezaY),
      radioCabeza,
      relleno,
    );

    // Cabello: casquete sobre la mitad superior.
    final Color? yelmo = equipo[RanuraItem.cabeza];
    if (yelmo == null) {
      relleno.color = cabello;
      lienzo.drawArc(
        Rect.fromCircle(
          center: Offset(s * 0.5, s * centroCabezaY),
          radius: radioCabeza * 1.08,
        ),
        3.14159,
        3.14159,
        true,
        relleno,
      );
    }

    // Ojos: dos puntos, siempre visibles.
    relleno.color = paleta.fondo.withValues(alpha: 0.85);
    lienzo
      ..drawCircle(
        Offset(s * 0.468, s * (centroCabezaY + 0.005)),
        s * 0.011,
        relleno,
      )
      ..drawCircle(
        Offset(s * 0.532, s * (centroCabezaY + 0.005)),
        s * 0.011,
        relleno,
      );

    // Yelmo por encima del cabello.
    if (yelmo != null) {
      relleno.color = yelmo;
      lienzo
        ..drawArc(
          Rect.fromCircle(
            center: Offset(s * 0.5, s * centroCabezaY),
            radius: radioCabeza * 1.16,
          ),
          3.14159,
          3.14159,
          true,
          relleno,
        )
        ..drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(
              s * 0.489,
              s * (centroCabezaY - 0.01),
              s * 0.022,
              s * 0.085,
            ),
            Radius.circular(s * 0.008),
          ),
          relleno,
        );
    }

    // Arma en la mano derecha.
    final Color? arma = equipo[RanuraItem.arma];
    if (arma != null) {
      final double x = s * (0.5 + ancho + 0.055);
      relleno.color = arma;
      lienzo
        ..drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(x - s * 0.014, s * 0.36, s * 0.028, s * 0.34),
            Radius.circular(s * 0.012),
          ),
          relleno,
        )
        ..drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(x - s * 0.055, s * 0.655, s * 0.11, s * 0.022),
            Radius.circular(s * 0.01),
          ),
          relleno,
        )
        ..drawCircle(Offset(x, s * 0.345), s * 0.026, relleno);
    }

    // Escudo en la mano izquierda.
    final Color? escudo = equipo[RanuraItem.secundaria];
    if (escudo != null) {
      final double x = s * (0.5 - ancho - 0.075);
      final double y = s * 0.60;
      final double w = s * 0.115;
      final Path forma = Path()
        ..moveTo(x - w / 2, y - w * 0.62)
        ..lineTo(x + w / 2, y - w * 0.62)
        ..lineTo(x + w / 2, y + w * 0.25)
        ..quadraticBezierTo(x, y + w * 0.95, x - w / 2, y + w * 0.25)
        ..close();
      relleno.color = escudo;
      lienzo.drawPath(forma, relleno);
      relleno.color = Color.lerp(escudo, paleta.textoPrimario, 0.35) ?? escudo;
      lienzo.drawCircle(Offset(x, y), w * 0.18, relleno);
    }
  }

  @override
  bool shouldRepaint(covariant _PintorAvatar anterior) =>
      anterior.piel != piel ||
      anterior.cabello != cabello ||
      anterior.esbelto != esbelto ||
      anterior.robusto != robusto ||
      anterior.resplandor != resplandor ||
      anterior.soloFondo != soloFondo ||
      !_mismoEquipo(anterior.equipo, equipo) ||
      anterior.paleta != paleta;

  static bool _mismoEquipo(Map<RanuraItem, Color> a, Map<RanuraItem, Color> b) {
    if (a.length != b.length) return false;
    for (final MapEntry<RanuraItem, Color> e in a.entries) {
      if (b[e.key] != e.value) return false;
    }
    return true;
  }
}

/// Una pieza del propio cuerpo: una mano.
///
/// Aparte de `_Capa` porque no es equipo: no se tiñe con el color de un ítem, no
/// se ajusta de talla ni de sitio —es del cuerpo, ya está donde tiene que
/// estar— y si faltara no hay ficha al margen que la sustituya.
class _CapaDelCuerpo extends StatelessWidget {
  const _CapaDelCuerpo({required this.ruta, required this.lado});

  final String ruta;
  final double lado;

  @override
  Widget build(BuildContext context) => Image.asset(
        ruta,
        height: lado,
        fit: BoxFit.contain,
        filterQuality: FilterQuality.medium,
        // Sin la mano el cuerpo sigue siendo un cuerpo. Mejor una figura sin
        // manos que una pantalla rota.
        errorBuilder: (BuildContext context, Object error, StackTrace? pila) =>
            const SizedBox.shrink(),
      );
}
