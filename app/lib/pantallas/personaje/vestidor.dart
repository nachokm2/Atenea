/// P16 — Vestidor: el personaje en grande, sus ranuras y su colección.
///
/// El avatar manda: ocupa el centro, y alrededor están las seis ranuras del
/// MVP. Tocar una ranura cambia la bandeja inferior; tocar un ítem lo equipa
/// al instante (el estado es optimista y revierte con aviso si el Reino dice
/// que no). Los ítems bloqueados se ven en silueta con su requisito, porque
/// saber qué falta motiva.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/personaje.dart';
import '../../estado/sesion.dart';
import '../../navegacion/rutas.dart';
import 'widgets/avatar_capas.dart';
import 'widgets/hoja_item.dart';
import 'widgets/piezas.dart';
import 'widgets/tarjeta_item.dart';

/// Pantalla del Vestidor.
class PantallaVestidor extends StatefulWidget {
  const PantallaVestidor({super.key});

  @override
  State<PantallaVestidor> createState() => _PantallaVestidorState();
}

class _PantallaVestidorState extends State<PantallaVestidor> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) => _preparar());
  }

  Future<void> _preparar() async {
    if (!mounted) return;
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();
    await personaje.cargarAvatar();
    if (!mounted) return;
    if (personaje.ranuraSeleccionada == null) {
      await personaje.seleccionarRanura(RanuraItem.cabeza);
    } else {
      await personaje.cargarInventario();
    }
  }

  Future<void> _tocarItem(ItemInventario fila) async {
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();

    if (!fila.poseido) {
      await _abrirFicha(fila.item.id);
      return;
    }

    if (fila.equipado) {
      final bool listo = await personaje.desequipar(fila.item.ranura);
      if (!mounted) return;
      if (!listo) {
        avisar(
          context,
          personaje.errorAvatar?.mensaje ?? 'No pudimos quitarlo.',
          esError: true,
        );
      }
      return;
    }

    if (!fila.puedeEquipar) {
      await _abrirFicha(fila.item.id);
      return;
    }

    final bool listo = await personaje.equipar(fila);
    if (!mounted) return;
    if (!listo) {
      avisar(
        context,
        personaje.errorAvatar?.mensaje ??
            'El Reino no pudo guardar el cambio. Volvimos a dejarlo como estaba.',
        esError: true,
      );
    }
  }

  Future<void> _abrirFicha(String itemId) async {
    final ResultadoFicha resultado =
        await mostrarFichaItem(context, itemId: itemId);
    if (!mounted) return;
    if (resultado.accion == AccionItem.irAlMercado) {
      context.go(Rutas.mercado);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ControladorPersonaje personaje = context.watch<ControladorPersonaje>();
    final ControladorSesion sesion = context.watch<ControladorSesion>();
    final RanuraItem ranura =
        personaje.ranuraSeleccionada ?? RanuraItem.cabeza;

    return PantallaAtenea(
      titulo: 'Vestidor',
      limitarAnchoLectura: false,
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        0,
        Espacio.md,
        Espacio.xl,
      ),
      acciones: <Widget>[
        ContadorOroActual(alTocar: () => context.go(Rutas.mercado)),
        IconButton(
          icon: const Icon(Icons.storefront_rounded),
          tooltip: 'Mercado',
          onPressed: () => context.go(Rutas.mercado),
        ),
      ],
      cuerpo: RefreshIndicator(
        onRefresh: () async {
          await personaje.cargarAvatar(forzar: true);
          await personaje.cargarInventario(forzar: true);
        },
        child: ListView(
          padding: EdgeInsets.zero,
          children: <Widget>[
            if (personaje.errorAvatar != null)
              BandaAviso(
                icono: Icons.undo_rounded,
                color: context.paleta.error,
                mensaje: personaje.errorAvatar!.mensaje,
                textoAccion: 'Entendido',
                alTocarAccion: personaje.limpiarErrores,
              ),
            _Escenario(
              personaje: personaje,
              ranuraActiva: ranura,
              nombre: sesion.personaje?.nombre,
              arquetipo: sesion.personaje?.arquetipo,
            ),
            const SizedBox(height: Espacio.md),
            _CabeceraBandeja(personaje: personaje, ranura: ranura),
            _Bandeja(
              personaje: personaje,
              ranura: ranura,
              alTocarItem: _tocarItem,
              alVerFicha: (String itemId) => _abrirFicha(itemId),
            ),
            const SizedBox(height: Espacio.lg),
            BotonPrimario(
              texto: 'Ir al Mercado',
              subtitulo: 'Gasta el oro que ganaste aprendiendo',
              icono: Icons.storefront_rounded,
              alTocar: () => context.go(Rutas.mercado),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Escenario: avatar con sus ranuras alrededor
// ---------------------------------------------------------------------------

class _Escenario extends StatelessWidget {
  const _Escenario({
    required this.personaje,
    required this.ranuraActiva,
    this.nombre,
    this.arquetipo,
  });

  final ControladorPersonaje personaje;
  final RanuraItem ranuraActiva;
  final String? nombre;
  final Arquetipo? arquetipo;

  @override
  Widget build(BuildContext context) {
    const List<RanuraItem> izquierda = <RanuraItem>[
      RanuraItem.cabeza,
      RanuraItem.cuerpo,
      RanuraItem.arma,
    ];
    const List<RanuraItem> derecha = <RanuraItem>[
      RanuraItem.capa,
      RanuraItem.accesorio,
      RanuraItem.secundaria,
    ];

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints medidas) {
        final double lado = (medidas.maxWidth - 2 * 72 - 2 * Espacio.sm)
            .clamp(140.0, 260.0)
            .toDouble();
        return Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            _ColumnaRanuras(
              ranuras: izquierda,
              activa: ranuraActiva,
              personaje: personaje,
            ),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Column(
                children: <Widget>[
                  RetratoAvatar(
                    capas: personaje.capas,
                    rasgos: personaje.avatar?.rasgos,
                    nombre: nombre,
                    subtitulo: arquetipo?.etiqueta,
                    tamano: lado,
                    cargando:
                        personaje.cargandoAvatar && personaje.avatar == null,
                  ),
                ],
              ),
            ),
            const SizedBox(width: Espacio.sm),
            _ColumnaRanuras(
              ranuras: derecha,
              activa: ranuraActiva,
              personaje: personaje,
            ),
          ],
        );
      },
    );
  }
}

class _ColumnaRanuras extends StatelessWidget {
  const _ColumnaRanuras({
    required this.ranuras,
    required this.activa,
    required this.personaje,
  });

  final List<RanuraItem> ranuras;
  final RanuraItem activa;
  final ControladorPersonaje personaje;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (final RanuraItem ranura in ranuras)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: Espacio.xxs),
            child: _BotonRanura(
              ranura: ranura,
              activa: ranura == activa,
              ocupada: personaje.equipadoEn(ranura) != null,
              guardando: personaje.ranuraGuardando == ranura,
              alTocar: () => personaje.seleccionarRanura(ranura),
            ),
          ),
      ],
    );
  }
}

class _BotonRanura extends StatelessWidget {
  const _BotonRanura({
    required this.ranura,
    required this.activa,
    required this.ocupada,
    required this.guardando,
    required this.alTocar,
  });

  final RanuraItem ranura;
  final bool activa;
  final bool ocupada;
  final bool guardando;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color acento = activa ? p.arcano : (ocupada ? p.oro : p.borde);

    return Semantics(
      label: '${nombreRanura(ranura)}. '
          '${ocupada ? 'Con equipamiento' : 'Ranura vacía'}',
      selected: activa,
      button: true,
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Material(
            color: activa
                ? p.arcano.withValues(alpha: 0.16)
                : p.superficie,
            borderRadius: Redondeo.rTarjeta,
            child: InkWell(
              onTap: alTocar,
              borderRadius: Redondeo.rTarjeta,
              child: AnimatedContainer(
                duration: Movimiento.micro,
                curve: Movimiento.estandar,
                height: Medida.areaTactilMin + 4,
                width: Medida.areaTactilMin + 4,
                decoration: BoxDecoration(
                  borderRadius: Redondeo.rTarjeta,
                  border: Border.all(
                    color: acento,
                    width: activa ? 1.8 : 1,
                  ),
                ),
                child: guardando
                    ? Center(
                        child: SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: p.arcano,
                          ),
                        ),
                      )
                    : Icon(
                        iconoDeRanura(ranura),
                        color: ocupada ? p.oro : p.textoSecundario,
                      ),
              ),
            ),
          ),
          const SizedBox(height: 2),
          SizedBox(
            width: 68,
            child: Text(
              nombreRanura(ranura),
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: context.textos.bodySmall?.copyWith(
                color: activa ? p.textoPrimario : p.textoSecundario,
                fontWeight: activa ? FontWeight.w800 : FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Bandeja de la ranura seleccionada
// ---------------------------------------------------------------------------

class _CabeceraBandeja extends StatelessWidget {
  const _CabeceraBandeja({required this.personaje, required this.ranura});

  final ControladorPersonaje personaje;
  final RanuraItem ranura;

  @override
  Widget build(BuildContext context) {
    final int total = personaje.inventario.length;
    final int poseidos = personaje.poseidos;
    final String conteo = total == 0 ? '' : '$poseidos de $total';

    return EncabezadoSeccion(
      titulo: nombreRanura(ranura).toUpperCase(),
      subtitulo: conteo.isEmpty ? null : '$conteo objetos en tu colección',
    );
  }
}

class _Bandeja extends StatelessWidget {
  const _Bandeja({
    required this.personaje,
    required this.ranura,
    required this.alTocarItem,
    required this.alVerFicha,
  });

  final ControladorPersonaje personaje;
  final RanuraItem ranura;
  final Future<void> Function(ItemInventario fila) alTocarItem;
  final void Function(String itemId) alVerFicha;

  @override
  Widget build(BuildContext context) {
    if (personaje.cargandoInventario && personaje.inventario.isEmpty) {
      return const _RejillaEsqueleto();
    }

    if (personaje.errorInventario != null && personaje.inventario.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: Espacio.lg),
        child: EstadoError(
          mensaje: personaje.errorInventario!.mensaje,
          alReintentar: () => personaje.cargarInventario(forzar: true),
        ),
      );
    }

    final List<ItemInventario> items = personaje.itemsDeLaRanura;
    if (items.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: Espacio.lg),
        child: EstadoVacio(
          icono: iconoDeRanura(ranura),
          titulo: 'Nada para ${nombreRanura(ranura).toLowerCase()} todavía',
          mensaje:
              'Los objetos llegan de dos formas: se ganan aprendiendo o se '
              'compran en el Mercado con el oro que ya ganaste.',
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        GridView.builder(
          padding: EdgeInsets.zero,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
            maxCrossAxisExtent: 172,
            mainAxisSpacing: Espacio.sm,
            crossAxisSpacing: Espacio.sm,
            childAspectRatio: 0.66,
          ),
          itemCount: items.length,
          itemBuilder: (BuildContext context, int i) {
            final ItemInventario fila = items[i];
            return TarjetaItem(
              item: fila.item,
              bloqueado: !fila.poseido,
              equipado: fila.equipado,
              esNuevo: fila.esNuevo,
              motivo: fila.motivoDesbloqueo,
              seGanaAprendiendo:
                  !fila.poseido && fila.item.seGanaAprendiendo,
              guardando: personaje.ranuraGuardando == fila.item.ranura,
              alTocar: () => alTocarItem(fila),
              alMantener: () => alVerFicha(fila.item.id),
            );
          },
        ),
        if (personaje.hayMasInventario) ...<Widget>[
          const SizedBox(height: Espacio.sm),
          Center(
            child: TextButton.icon(
              onPressed: personaje.cargandoMasInventario
                  ? null
                  : personaje.masInventario,
              icon: personaje.cargandoMasInventario
                  ? const SizedBox(
                      height: 16,
                      width: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.expand_more_rounded),
              label: const Text('Ver más objetos'),
            ),
          ),
        ],
        const SizedBox(height: Espacio.xs),
        Text(
          'Mantén pulsado un objeto para leer su historia.',
          textAlign: TextAlign.center,
          style: context.textos.bodySmall?.copyWith(
            color: context.paleta.textoSecundario,
          ),
        ),
      ],
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
        maxCrossAxisExtent: 172,
        mainAxisSpacing: Espacio.sm,
        crossAxisSpacing: Espacio.sm,
        childAspectRatio: 0.66,
      ),
      itemCount: 4,
      itemBuilder: (BuildContext context, int i) => const EsqueletoItem(),
    );
  }
}
