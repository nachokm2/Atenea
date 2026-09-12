/// Hojas de detalle de un ítem: ficha, confirmación de compra y celebración de
/// la compra (§3.3 regla 4: los detalles se abren como hoja, nunca como
/// pantalla nueva).
///
/// Ninguna de estas hojas calcula oro: el precio y el saldo vienen del Reino y
/// el saldo posterior a la compra lo devuelve el propio servidor.
library;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:provider/provider.dart';

import '../../../data/errores.dart';
import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';
import '../../../estado/personaje.dart';
import '../../../navegacion/armazon.dart';
import 'avatar_capas.dart';
import 'piezas.dart';

/// Qué pidió el usuario al cerrar la ficha.
enum AccionItem {
  /// Cerró sin pedir nada (o equipó desde la propia ficha).
  ninguna,

  /// Quiere comprarlo: el Mercado sigue con la confirmación.
  comprar,

  /// Quiere verlo en el Mercado.
  irAlMercado,
}

/// Resultado de la ficha: acción y, si aplica, el anuncio implicado.
class ResultadoFicha {
  const ResultadoFicha(this.accion, {this.anuncioId});

  final AccionItem accion;
  final String? anuncioId;
}

/// Abre la ficha completa de un ítem.
Future<ResultadoFicha> mostrarFichaItem(
  BuildContext context, {
  required String itemId,
  bool enMercado = false,
}) async {
  final ResultadoFicha? resultado = await mostrarHoja<ResultadoFicha>(
    context,
    constructor: (BuildContext hoja) => _HojaFicha(
      itemId: itemId,
      enMercado: enMercado,
    ),
  );
  return resultado ?? const ResultadoFicha(AccionItem.ninguna);
}

class _HojaFicha extends StatefulWidget {
  const _HojaFicha({required this.itemId, required this.enMercado});

  final String itemId;
  final bool enMercado;

  @override
  State<_HojaFicha> createState() => _HojaFichaState();
}

class _HojaFichaState extends State<_HojaFicha> {
  DetalleItem? _detalle;
  bool _cargando = true;
  bool _guardando = false;
  ErrorAtenea? _error;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();
    final DetalleItem? detalle = await personaje.ficha(widget.itemId);
    if (!mounted) return;
    setState(() {
      _detalle = detalle;
      _error = detalle == null ? personaje.errorInventario : null;
      _cargando = false;
    });
  }

  Future<void> _equipar(ItemInventario item) async {
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();
    setState(() => _guardando = true);
    final bool listo = await personaje.equipar(item);
    if (!mounted) return;
    setState(() => _guardando = false);
    if (listo) {
      avisar(context, '${item.item.nombre} equipado.');
      Navigator.of(context).pop(const ResultadoFicha(AccionItem.ninguna));
    } else {
      avisar(
        context,
        personaje.errorAvatar?.mensaje ??
            'No pudimos equiparlo. Inténtalo otra vez.',
        esError: true,
      );
    }
  }

  Future<void> _quitar(RanuraItem ranura) async {
    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();
    setState(() => _guardando = true);
    final bool listo = await personaje.desequipar(ranura);
    if (!mounted) return;
    setState(() => _guardando = false);
    if (listo) {
      avisar(context, '${nombreRanura(ranura)}: ranura libre.');
      Navigator.of(context).pop(const ResultadoFicha(AccionItem.ninguna));
    } else {
      avisar(
        context,
        personaje.errorAvatar?.mensaje ?? 'No pudimos quitarlo.',
        esError: true,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final double maximo = MediaQuery.sizeOf(context).height * 0.88;

    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: maximo),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            Espacio.md,
            Espacio.xs,
            Espacio.md,
            Espacio.md,
          ),
          child: _cuerpo(context),
        ),
      ),
    );
  }

  Widget _cuerpo(BuildContext context) {
    if (_cargando) {
      return const SizedBox(
        height: 260,
        child: EstadoCarga(mensaje: 'Abriendo la ficha…'),
      );
    }

    final DetalleItem? detalle = _detalle;
    if (detalle == null) {
      return SizedBox(
        height: 260,
        child: EstadoError(
          mensaje: _error?.mensaje ??
              'No pudimos abrir la ficha de este objeto ahora mismo.',
          alReintentar: _cargar,
        ),
      );
    }

    return _FichaCargada(
      detalle: detalle,
      enMercado: widget.enMercado,
      guardando: _guardando,
      alEquipar: _equipar,
      alQuitar: _quitar,
    );
  }
}

class _FichaCargada extends StatelessWidget {
  const _FichaCargada({
    required this.detalle,
    required this.enMercado,
    required this.guardando,
    required this.alEquipar,
    required this.alQuitar,
  });

  final DetalleItem detalle;
  final bool enMercado;
  final bool guardando;
  final Future<void> Function(ItemInventario item) alEquipar;
  final Future<void> Function(RanuraItem ranura) alQuitar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ItemInventario fila = detalle.inventario;
    final Item item = detalle.item;
    final Rareza rareza = rarezaVisualDe(item.rareza);
    final ControladorPersonaje personaje = context.watch<ControladorPersonaje>();
    final List<CapaAvatar> vistaPrevia =
        capasConItem(personaje.capas, item);

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              SizedBox(
                width: 132,
                child: AvatarCapas(
                  capas: vistaPrevia,
                  rasgos: personaje.avatar?.rasgos,
                  tamano: 132,
                ),
              ),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(item.nombre, style: context.textos.displaySmall),
                    const SizedBox(height: Espacio.xs),
                    Wrap(
                      spacing: Espacio.xs,
                      runSpacing: Espacio.xxs,
                      children: <Widget>[
                        ChipRareza(rareza: rareza),
                        Pildora(
                          texto: nombreRanura(item.ranura),
                          icono: iconoDeRanura(item.ranura),
                        ),
                        Pildora(
                          texto: item.origen.etiqueta,
                          color: item.seGanaAprendiendo ? p.dominio : null,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (item.descripcion != null) ...<Widget>[
            const SizedBox(height: Espacio.md),
            Text(
              item.descripcion!,
              style: context.textos.bodyLarge?.copyWith(
                color: p.textoSecundario,
              ),
            ),
          ],
          if (item.nombreConocimiento != null) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            Pildora(
              texto: 'Territorio: ${item.nombreConocimiento}',
              icono: Icons.terrain_rounded,
              color: p.dominio,
            ),
          ],
          if (fila.poseido && fila.adquiridoEn != null) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            FilaDato(
              etiqueta: 'Lo conseguiste',
              valor: fechaConAno(fila.adquiridoEn!),
              icono: Icons.event_available_rounded,
            ),
          ],
          if (!fila.poseido) ...<Widget>[
            const SizedBox(height: Espacio.md),
            Text(
              item.seGanaAprendiendo
                  ? 'Este objeto no se compra: se gana aprendiendo.'
                  : 'Cómo se consigue',
              style: context.textos.titleMedium,
            ),
            const SizedBox(height: Espacio.xs),
            if (fila.motivoDesbloqueo != null)
              Padding(
                padding: const EdgeInsets.only(bottom: Espacio.xs),
                child: Text(
                  fila.motivoDesbloqueo!,
                  style: context.textos.bodyMedium?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
              ),
            ListaRequisitos(requisitos: fila.requisitos),
          ],
          if (detalle.precio != null && !fila.poseido) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            FilaDato(
              etiqueta: 'Precio',
              valor: '${cifra(detalle.precio!)} de oro',
              icono: Icons.local_offer_rounded,
            ),
            FilaDato(
              etiqueta: 'Tu oro',
              valor: cifra(detalle.saldoOro),
              icono: Icons.monetization_on_rounded,
            ),
            if (detalle.oroFaltante > 0)
              Padding(
                padding: const EdgeInsets.only(top: Espacio.xs),
                child: BandaAviso(
                  icono: Icons.savings_rounded,
                  color: p.oro,
                  mensaje:
                      'Te faltan ${cifra(detalle.oroFaltante)} de oro. Una '
                      'lección más y es tuyo.',
                ),
              ),
          ],
          const SizedBox(height: Espacio.lg),
          ..._acciones(context, fila),
        ],
      ),
    );
  }

  List<Widget> _acciones(BuildContext context, ItemInventario fila) {
    final Item item = detalle.item;
    final String? anuncioId = detalle.anuncioId;

    if (fila.equipado) {
      return <Widget>[
        BotonPrimario(
          texto: 'Quitar',
          icono: Icons.remove_circle_outline_rounded,
          cargando: guardando,
          alTocar: () => alQuitar(item.ranura),
        ),
      ];
    }

    if (fila.poseido) {
      return <Widget>[
        BotonPrimario(
          texto: 'Equipar',
          subtitulo: nombreRanura(item.ranura),
          icono: Icons.checkroom_rounded,
          cargando: guardando,
          alTocar: fila.puedeEquipar ? () => alEquipar(fila) : null,
        ),
        if (!fila.puedeEquipar)
          Padding(
            padding: const EdgeInsets.only(top: Espacio.xs),
            child: Text(
              'Este objeto forma parte de tu atuendo base.',
              textAlign: TextAlign.center,
              style: context.textos.bodySmall?.copyWith(
                color: context.paleta.textoSecundario,
              ),
            ),
          ),
      ];
    }

    if (item.seGanaAprendiendo || anuncioId == null) {
      return <Widget>[
        OutlinedButton.icon(
          onPressed: () => Navigator.of(context).pop(
            const ResultadoFicha(AccionItem.ninguna),
          ),
          icon: const Icon(Icons.auto_stories_rounded),
          label: const Text('Entendido'),
        ),
      ];
    }

    if (!enMercado) {
      return <Widget>[
        BotonPrimario(
          texto: 'Verlo en el Mercado',
          icono: Icons.storefront_rounded,
          alTocar: () => Navigator.of(context).pop(
            ResultadoFicha(AccionItem.irAlMercado, anuncioId: anuncioId),
          ),
        ),
      ];
    }

    final bool disponible = detalle.puedeComprar && detalle.oroFaltante == 0;
    return <Widget>[
      BotonPrimario(
        texto: 'Comprar por ${cifra(detalle.precio ?? 0)}',
        subtitulo: disponible ? null : 'Todavía no está a tu alcance',
        icono: Icons.monetization_on_rounded,
        alTocar: disponible
            ? () => Navigator.of(context).pop(
                  ResultadoFicha(AccionItem.comprar, anuncioId: anuncioId),
                )
            : null,
      ),
    ];
  }
}

// ---------------------------------------------------------------------------
// Confirmación de compra
// ---------------------------------------------------------------------------

/// Confirma una compra mostrando el precio y el oro disponible.
///
/// El saldo resultante no se calcula aquí: lo devuelve el servidor y se
/// muestra en la celebración posterior.
Future<bool> confirmarCompra(
  BuildContext context, {
  required Anuncio anuncio,
  required int saldo,
}) async {
  final bool? confirmado = await mostrarHoja<bool>(
    context,
    constructor: (BuildContext hoja) {
      final AteneaPalette p = hoja.paleta;
      final Rareza rareza = rarezaVisualDe(anuncio.item.rareza);
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            Espacio.md,
            Espacio.xs,
            Espacio.md,
            Espacio.md,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text('Confirma tu compra', style: hoja.textos.headlineSmall),
              const SizedBox(height: Espacio.md),
              Row(
                children: <Widget>[
                  Container(
                    height: 56,
                    width: 56,
                    decoration: BoxDecoration(
                      color: rareza.color.withValues(alpha: 0.12),
                      borderRadius: Redondeo.rChip,
                      border: Border.all(
                        color: rareza.color.withValues(alpha: 0.4),
                      ),
                    ),
                    child: Icon(
                      iconoDeRanura(anuncio.item.ranura),
                      color: rareza.color,
                    ),
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          anuncio.item.nombre,
                          style: hoja.textos.titleLarge,
                        ),
                        const SizedBox(height: Espacio.xxs),
                        ChipRareza(rareza: rareza),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: Espacio.md),
              FilaDato(
                etiqueta: 'Precio',
                valor: cifra(anuncio.precio),
                icono: Icons.local_offer_rounded,
              ),
              FilaDato(
                etiqueta: 'Tu oro antes de comprar',
                valor: cifra(saldo),
                icono: Icons.monetization_on_rounded,
              ),
              const SizedBox(height: Espacio.xs),
              Text(
                'El oro se gana aprendiendo y aquí solo compra apariencia: '
                'nada de esto cambia lo que aprendes.',
                style: hoja.textos.bodySmall?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
              const SizedBox(height: Espacio.lg),
              BotonPrimario(
                texto: 'Comprar',
                icono: Icons.check_rounded,
                alTocar: () => Navigator.of(hoja).pop(true),
              ),
              const SizedBox(height: Espacio.xs),
              TextButton(
                onPressed: () => Navigator.of(hoja).pop(false),
                child: const Text('Ahora no'),
              ),
            ],
          ),
        ),
      );
    },
  );
  return confirmado ?? false;
}

// ---------------------------------------------------------------------------
// Celebración de la compra
// ---------------------------------------------------------------------------

/// Qué pidió el usuario tras una compra bien hecha.
enum AccionCompra { cerrar, equipar, deshacer }

/// Muestra la compra recién hecha con las monedas volando hacia el contador.
Future<AccionCompra> mostrarCompraLista(
  BuildContext context, {
  required Compra compra,
  required Item item,
}) async {
  final AccionCompra? accion = await mostrarHoja<AccionCompra>(
    context,
    constructor: (BuildContext hoja) => _HojaCompra(compra: compra, item: item),
  );
  return accion ?? AccionCompra.cerrar;
}

class _HojaCompra extends StatelessWidget {
  const _HojaCompra({required this.compra, required this.item});

  final Compra compra;
  final Item item;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Rareza rareza = rarezaVisualDe(item.rareza);
    final bool quieto = reducirMovimiento(context);
    final bool puedeEquipar = compra.itemUsuario?.puedeEquipar ?? true;

    Widget emblema = Container(
      height: 96,
      width: 96,
      decoration: BoxDecoration(
        color: rareza.color.withValues(alpha: 0.14),
        shape: BoxShape.circle,
        border: Border.all(color: rareza.color, width: 1.5),
        boxShadow: quieto ? null : Sombra.brillo(rareza.color, rareza.brillo),
      ),
      child: Icon(
        iconoDeRanura(item.ranura),
        size: 44,
        color: rareza.color,
      ),
    );
    if (!quieto) {
      emblema = emblema
          .animate()
          .scale(
            duration: Movimiento.corta,
            curve: Movimiento.entrada,
            begin: const Offset(0.7, 0.7),
            end: const Offset(1, 1),
          )
          .fadeIn(duration: Movimiento.corta);
    }

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          Espacio.md,
          Espacio.xs,
          Espacio.md,
          Espacio.md,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Center(child: emblema),
            const SizedBox(height: Espacio.md),
            Text(
              'Ya es tuyo',
              textAlign: TextAlign.center,
              style: context.textos.displaySmall,
            ),
            const SizedBox(height: Espacio.xxs),
            Text(
              item.nombre,
              textAlign: TextAlign.center,
              style: context.textos.bodyLarge?.copyWith(
                color: p.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.md),
            Center(
              child: Semantics(
                label: 'Te quedan ${compra.saldoDespues} de oro',
                excludeSemantics: true,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(
                      Icons.monetization_on_rounded,
                      color: p.oro,
                      size: 22,
                    ),
                    const SizedBox(width: Espacio.xs),
                    CifraAnimada(
                      valor: compra.saldoDespues,
                      estilo: Cifras.grande(context).copyWith(color: p.oro),
                      duracion: Movimiento.celebracion,
                    ),
                    const SizedBox(width: Espacio.xs),
                    Text(
                      'de oro',
                      style: context.textos.bodyMedium?.copyWith(
                        color: p.textoSecundario,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: Espacio.lg),
            BotonPrimario(
              texto: puedeEquipar ? 'Equipar ahora' : 'Ver en el Vestidor',
              icono: Icons.checkroom_rounded,
              alTocar: () => Navigator.of(context).pop(AccionCompra.equipar),
            ),
            const SizedBox(height: Espacio.xs),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: <Widget>[
                TextButton(
                  onPressed: () =>
                      Navigator.of(context).pop(AccionCompra.deshacer),
                  child: const Text('Deshacer compra'),
                ),
                TextButton(
                  onPressed: () =>
                      Navigator.of(context).pop(AccionCompra.cerrar),
                  child: const Text('Seguir mirando'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
