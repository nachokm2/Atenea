/// P15 — Mercado: gastar el oro ganado aprendiendo.
///
/// Aquí solo se compra apariencia. No hay dinero real, no hay ventaja
/// educativa y el precio siempre lo fija el Reino: la pantalla envía el precio
/// que mostró (`precioEsperado`) para que el servidor rechace la compra si
/// cambió mientras el usuario decidía.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/personaje.dart';
import '../../navegacion/rutas.dart';
import 'widgets/hoja_item.dart';
import 'widgets/piezas.dart';
import 'widgets/tarjeta_item.dart';

/// Pantalla del Mercado.
class PantallaMercado extends StatefulWidget {
  const PantallaMercado({super.key});

  @override
  State<PantallaMercado> createState() => _PantallaMercadoState();
}

class _PantallaMercadoState extends State<PantallaMercado> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      final ControladorPersonaje personaje =
          context.read<ControladorPersonaje>();
      personaje.cargarTienda();
      personaje.cargarAvatar();
    });
  }

  // -------------------------------------------------------------------------
  // Acciones
  // -------------------------------------------------------------------------

  Future<void> _abrirFicha(Anuncio anuncio) async {
    final ResultadoFicha resultado = await mostrarFichaItem(
      context,
      itemId: anuncio.item.id,
      enMercado: true,
      anuncio: anuncio,
      saldoOro: context.read<ControladorPersonaje>().saldo,
    );
    if (!mounted) return;
    if (resultado.accion == AccionItem.comprar) {
      await _comprar(anuncio);
    }
  }

  Future<void> _comprar(Anuncio anuncio) async {
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();

    if (!anuncio.puedeComprar) {
      avisar(
        context,
        anuncio.motivoBloqueo ?? 'Todavía no puedes llevarte este objeto.',
        esError: true,
      );
      return;
    }

    final bool confirmado = await confirmarCompra(
      context,
      anuncio: anuncio,
      saldo: personaje.saldo,
    );
    if (!mounted || !confirmado) return;

    final Compra? compra = await personaje.comprar(anuncio);
    if (!mounted) return;

    if (compra == null) {
      avisar(
        context,
        personaje.errorTienda?.mensaje ??
            'No pudimos completar la compra. Tu oro sigue intacto.',
        esError: true,
      );
      return;
    }

    final AccionCompra accion = await mostrarCompraLista(
      context,
      compra: compra,
      item: anuncio.item,
    );
    if (!mounted) return;

    switch (accion) {
      case AccionCompra.equipar:
        await _equiparCompra(compra);
      case AccionCompra.deshacer:
        await _deshacer(compra);
      case AccionCompra.cerrar:
        break;
    }
    if (!mounted) return;
    personaje.olvidarCompra();
  }

  Future<void> _equiparCompra(Compra compra) async {
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();
    final ItemInventario? fila = compra.itemUsuario;
    if (fila == null || !fila.puedeEquipar) {
      context.go(Rutas.personaje);
      return;
    }
    final bool listo = await personaje.equipar(fila);
    if (!mounted) return;
    if (listo) {
      avisar(context, '${fila.item.nombre} equipado. Te queda bien.');
      context.go(Rutas.personaje);
    } else {
      avisar(
        context,
        personaje.errorAvatar?.mensaje ?? 'No pudimos equiparlo ahora.',
        esError: true,
      );
    }
  }

  Future<void> _deshacer(Compra compra) async {
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();
    final bool listo = await personaje.deshacerCompra(compra.orden.id);
    if (!mounted) return;
    avisar(
      context,
      listo
          ? 'Compra deshecha. Tu oro volvió a tu bolsa.'
          : personaje.errorTienda?.mensaje ??
              'No pudimos deshacer la compra.',
      esError: !listo,
    );
  }

  // -------------------------------------------------------------------------
  // Construcción
  // -------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorPersonaje personaje = context.watch<ControladorPersonaje>();
    final Tienda? tienda = personaje.tienda;

    return PantallaAtenea(
      titulo: 'Mercado',
      mostrarVolver: true,
      limitarAnchoLectura: false,
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        0,
        Espacio.md,
        Espacio.xl,
      ),
      acciones: <Widget>[
        ContadorOroActual(alTocar: () => context.push(Rutas.monedero)),
      ],
      cuerpo: RefreshIndicator(
        onRefresh: () => personaje.cargarTienda(forzar: true),
        child: _cuerpo(context, personaje, tienda),
      ),
    );
  }

  Widget _cuerpo(
    BuildContext context,
    ControladorPersonaje personaje,
    Tienda? tienda,
  ) {
    if (tienda == null && personaje.cargandoTienda) {
      return ListView(
        padding: EdgeInsets.zero,
        children: const <Widget>[
          SizedBox(height: Espacio.md),
          EsqueletoFilas(filas: 1, alto: 40),
          SizedBox(height: Espacio.sm),
          _RejillaEsqueleto(),
        ],
      );
    }

    if (tienda == null) {
      return ListView(
        padding: EdgeInsets.zero,
        children: <Widget>[
          const SizedBox(height: Espacio.xxl),
          EstadoError(
            titulo: 'El Mercado está cerrado un momento',
            mensaje: personaje.errorTienda?.mensaje ??
                'No pudimos traer el catálogo. Vuelve a intentarlo.',
            alReintentar: () => personaje.cargarTienda(forzar: true),
          ),
        ],
      );
    }

    final List<Anuncio> visibles = personaje.anunciosVisibles;
    final List<RanuraItem> categorias = <RanuraItem>[
      for (final RanuraItem r in ranurasDelVestidor)
        if (tienda.anuncios.any((Anuncio a) => a.item.ranura == r)) r,
    ];

    return ListView(
      padding: EdgeInsets.zero,
      children: <Widget>[
        if (personaje.errorTienda != null)
          BandaAviso(
            icono: Icons.wifi_off_rounded,
            mensaje:
                'Estás viendo el catálogo guardado. Comprar necesita conexión.',
            textoAccion: 'Reintentar',
            alTocarAccion: () => personaje.cargarTienda(forzar: true),
          ),
        _Filtros(
          personaje: personaje,
          categorias: categorias,
        ),
        if (tienda.destacados.isNotEmpty &&
            personaje.categoriaMercado == null &&
            !personaje.soloAlcanzables) ...<Widget>[
          const EncabezadoSeccion(
            titulo: 'Destacados de la semana',
            subtitulo: 'Lo que el Reino recomienda hoy',
          ),
          _Destacados(
            anuncios: tienda.destacados,
            alTocar: _abrirFicha,
          ),
        ],
        EncabezadoSeccion(
          titulo: 'Catálogo',
          subtitulo: personaje.soloAlcanzables
              ? 'Solo lo que puedes llevarte ahora'
              : 'Cosmético: nada de esto cambia lo que aprendes',
        ),
        if (visibles.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: Espacio.lg),
            child: EstadoVacio(
              icono: Icons.search_off_rounded,
              titulo: 'Nada aquí todavía',
              mensaje:
                  'Prueba con otra categoría o quita el filtro: el Mercado '
                  'cambia a medida que subes de nivel.',
              textoAccion: personaje.soloAlcanzables ||
                      personaje.categoriaMercado != null
                  ? 'Ver todo el catálogo'
                  : null,
              alTocarAccion: () {
                personaje.fijarCategoria(null);
                if (personaje.soloAlcanzables) personaje.alternarAlcanzables();
              },
            ),
          )
        else
          GridView.builder(
            padding: EdgeInsets.zero,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 180,
              mainAxisSpacing: Espacio.sm,
              crossAxisSpacing: Espacio.sm,
              childAspectRatio: 0.64,
            ),
            itemCount: visibles.length,
            itemBuilder: (BuildContext context, int i) {
              final Anuncio anuncio = visibles[i];
              return TarjetaItem(
                item: anuncio.item,
                bloqueado: !anuncio.puedeComprar && !anuncio.poseido,
                equipado: false,
                precio: anuncio.precio,
                puedePagar: anuncio.puedePagar,
                motivo: anuncio.poseido
                    ? 'Ya es tuyo'
                    : anuncio.motivoBloqueo,
                alTocar: () => _abrirFicha(anuncio),
              );
            },
          ),
        if (tienda.itemsDeConocimiento.isNotEmpty) ...<Widget>[
          const EncabezadoSeccion(
            titulo: 'Se ganan aprendiendo',
            subtitulo: 'Estos no se compran: los entrega tu propio progreso',
          ),
          for (final Anuncio anuncio in tienda.itemsDeConocimiento)
            Padding(
              padding: const EdgeInsets.only(bottom: Espacio.sm),
              child: _FilaConocimiento(
                anuncio: anuncio,
                alTocar: () => _abrirFicha(anuncio),
              ),
            ),
        ],
        const SizedBox(height: Espacio.md),
        Text(
          'El oro solo se gana aprendiendo y solo compra apariencia.',
          textAlign: TextAlign.center,
          style: context.textos.bodySmall?.copyWith(
            color: context.paleta.textoSecundario,
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Filtros
// ---------------------------------------------------------------------------

class _Filtros extends StatelessWidget {
  const _Filtros({required this.personaje, required this.categorias});

  final ControladorPersonaje personaje;
  final List<RanuraItem> categorias;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        const SizedBox(height: Espacio.xs),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: <Widget>[
              _Chip(
                texto: 'Todo',
                icono: Icons.grid_view_rounded,
                activo: personaje.categoriaMercado == null,
                alTocar: () => personaje.fijarCategoria(null),
              ),
              for (final RanuraItem r in categorias)
                _Chip(
                  texto: nombreRanura(r),
                  icono: iconoDeRanura(r),
                  activo: personaje.categoriaMercado == r,
                  alTocar: () => personaje.fijarCategoria(r),
                ),
            ],
          ),
        ),
        const SizedBox(height: Espacio.xs),
        Row(
          children: <Widget>[
            _Chip(
              texto: 'Puedo comprar',
              icono: Icons.monetization_on_rounded,
              activo: personaje.soloAlcanzables,
              color: p.oro,
              alTocar: personaje.alternarAlcanzables,
            ),
          ],
        ),
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({
    required this.texto,
    required this.activo,
    required this.alTocar,
    this.icono,
    this.color,
  });

  final String texto;
  final bool activo;
  final VoidCallback alTocar;
  final IconData? icono;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color acento = color ?? p.arcano;

    return Padding(
      padding: const EdgeInsets.only(right: Espacio.xs),
      child: ChoiceChip(
        selected: activo,
        onSelected: (bool _) => alTocar(),
        showCheckmark: false,
        avatar: icono == null
            ? null
            : Icon(
                icono,
                size: 16,
                color: activo ? acento : p.textoSecundario,
              ),
        label: Text(texto),
        labelStyle: context.textos.bodySmall?.copyWith(
          fontWeight: FontWeight.w700,
          color: activo ? p.textoPrimario : p.textoSecundario,
        ),
        selectedColor: acento.withValues(alpha: 0.18),
        side: BorderSide(color: activo ? acento : p.borde),
        materialTapTargetSize: MaterialTapTargetSize.padded,
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Destacados
// ---------------------------------------------------------------------------

class _Destacados extends StatelessWidget {
  const _Destacados({required this.anuncios, required this.alTocar});

  final List<Anuncio> anuncios;
  final Future<void> Function(Anuncio anuncio) alTocar;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 268,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.zero,
        itemCount: anuncios.length,
        separatorBuilder: (BuildContext context, int i) =>
            const SizedBox(width: Espacio.sm),
        itemBuilder: (BuildContext context, int i) {
          final Anuncio anuncio = anuncios[i];
          return SizedBox(
            width: 168,
            child: TarjetaItem(
              item: anuncio.item,
              bloqueado: !anuncio.puedeComprar && !anuncio.poseido,
              precio: anuncio.precio,
              puedePagar: anuncio.puedePagar,
              motivo: anuncio.poseido ? 'Ya es tuyo' : anuncio.motivoBloqueo,
              alTocar: () => alTocar(anuncio),
            ),
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Ítems que se ganan aprendiendo
// ---------------------------------------------------------------------------

class _FilaConocimiento extends StatelessWidget {
  const _FilaConocimiento({required this.anuncio, required this.alTocar});

  final Anuncio anuncio;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Rareza rareza = rarezaVisualDe(anuncio.item.rareza);
    final Requisito? pendiente = requisitoPendiente(anuncio.requisitos);
    final String requisito = anuncio.motivoBloqueo ??
        pendiente?.etiqueta ??
        'Avanza en su territorio para ganarlo';

    return TarjetaAtenea(
      alTocar: alTocar,
      semantica: '${anuncio.item.nombre}. ${rareza.etiqueta}. $requisito',
      hijo: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Container(
            height: 56,
            width: 56,
            decoration: BoxDecoration(
              color: p.fondo.withValues(alpha: 0.5),
              borderRadius: Redondeo.rChip,
              border: Border.all(color: p.borde),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: <Widget>[
                Icon(
                  iconoDeRanura(anuncio.item.ranura),
                  color: p.textoSecundario.withValues(alpha: 0.35),
                ),
                Icon(Icons.lock_rounded, size: 18, color: p.textoSecundario),
              ],
            ),
          ),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(anuncio.item.nombre, style: context.textos.titleMedium),
                const SizedBox(height: Espacio.xxs),
                Wrap(
                  spacing: Espacio.xs,
                  runSpacing: Espacio.xxs,
                  children: <Widget>[
                    ChipRareza(rareza: rareza),
                    Pildora(
                      texto: 'Se gana aprendiendo',
                      icono: Icons.school_rounded,
                      color: p.dominio,
                    ),
                  ],
                ),
                const SizedBox(height: Espacio.xs),
                Text(
                  requisito,
                  style: context.textos.bodyMedium?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
                if (pendiente != null && pendiente.objetivo > 0) ...<Widget>[
                  const SizedBox(height: Espacio.xs),
                  BarraProgreso(
                    valor: pendiente.fraccion,
                    alto: 6,
                    color: p.dominio,
                    textoDerecha:
                        '${cifra(pendiente.actual.round())} / ${cifra(pendiente.objetivo.round())}',
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RejillaEsqueleto extends StatelessWidget {
  const _RejillaEsqueleto();

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 180,
        mainAxisSpacing: Espacio.sm,
        crossAxisSpacing: Espacio.sm,
        childAspectRatio: 0.64,
      ),
      itemCount: 6,
      itemBuilder: (BuildContext context, int i) => const EsqueletoItem(),
    );
  }
}
