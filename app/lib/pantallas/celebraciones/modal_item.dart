/// P14 — Modal de ítem desbloqueado.
///
/// Hace tangible que el aprendizaje se convierte en equipamiento: marco con el
/// color de la rareza, motivo del desbloqueo y la posibilidad de equiparlo con
/// un solo toque, sin salir de la celebración.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/celebraciones.dart';
import '../../estado/personaje.dart';
import '../../navegacion/rutas.dart';
import 'marco_celebracion.dart';

/// Overlay de ítem desbloqueado, con "Equipar ahora".
class ModalItemDesbloqueado extends StatefulWidget {
  const ModalItemDesbloqueado({required this.celebracion, super.key});

  /// Celebración que la cola dejó al frente.
  final Celebracion celebracion;

  @override
  State<ModalItemDesbloqueado> createState() => _ModalItemDesbloqueadoState();
}

class _ModalItemDesbloqueadoState extends State<ModalItemDesbloqueado> {
  bool _equipando = false;

  ItemRecibo? get _item => widget.celebracion.item;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final ItemRecibo? item = _item;
    final Rareza rareza = widget.celebracion.rarezaVisual;
    final bool quieto = reducirMovimiento(context);

    if (item == null) {
      return MarcoCelebracion(
        acento: p.oro,
        semantica: widget.celebracion.semantica,
        contenido: Text(
          widget.celebracion.titulo,
          textAlign: TextAlign.center,
          style: context.textos.headlineSmall,
        ),
        acciones: <Widget>[
          BotonPrimario(texto: 'Continuar', alTocar: cola.descartar),
        ],
      );
    }

    return MarcoCelebracion(
      acento: rareza.color,
      brillo: rareza.brillo,
      hapticaFuerte: true,
      semantica: widget.celebracion.semantica,
      contenido: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          RotuloCelebracion(
            texto: 'Nuevo equipamiento',
            color: p.textoSecundario,
          ),
          const SizedBox(height: Espacio.md),
          Center(
            child: Container(
              width: 132,
              height: 132,
              decoration: BoxDecoration(
                color: rareza.color.withValues(alpha: 0.12),
                borderRadius: Redondeo.rTarjeta,
                border: Border.all(color: rareza.color, width: 2),
                boxShadow: quieto ? null : Sombra.brillo(rareza.color, rareza.brillo),
              ),
              child: Icon(
                _iconoDe(item.ranura),
                size: 64,
                color: rareza.color,
              ),
            ),
          ),
          const SizedBox(height: Espacio.md),
          Text(
            item.nombre,
            textAlign: TextAlign.center,
            style: context.textos.displaySmall,
          ),
          const SizedBox(height: Espacio.xs),
          Center(child: ChipRareza(rareza: rareza)),
          const SizedBox(height: Espacio.sm),
          Text(
            item.motivoDesbloqueo ??
                'Lo ganaste aprendiendo: ${item.origen.etiqueta.toLowerCase()}.',
            textAlign: TextAlign.center,
            style: context.textos.bodyLarge?.copyWith(color: p.textoSecundario),
          ),
          const SizedBox(height: Espacio.md),
          Center(
            child: Pildora(
              texto: 'Se lleva en: ${item.ranura.etiqueta}',
              icono: Icons.checkroom_rounded,
              color: p.textoSecundario,
            ),
          ),
        ],
      ),
      acciones: <Widget>[
        if (item.puedeEquipar)
          BotonPrimario(
            texto: 'Equipar ahora',
            icono: Icons.auto_fix_high_rounded,
            cargando: _equipando,
            alTocar: () => _equipar(item),
          ),
        TextButton(
          onPressed: _equipando ? null : cola.descartar,
          child: Text(
            item.puedeEquipar
                ? 'Guardar en el Vestidor'
                : 'Guardado en el Vestidor',
          ),
        ),
        if (!item.puedeEquipar)
          TextButton(
            onPressed: () {
              cola.descartar();
              context.go(Rutas.personaje);
            },
            child: const Text('Ir al Vestidor'),
          ),
      ],
    );
  }

  Future<void> _equipar(ItemRecibo item) async {
    if (_equipando) return;
    setState(() => _equipando = true);

    final ControladorPersonaje personaje = context.read<ControladorPersonaje>();
    await personaje.cargarAvatar();
    if (!mounted) return;

    final String? anterior = personaje.equipadoEn(item.ranura);
    final bool reemplaza =
        anterior != null && anterior != item.itemUsuarioId;

    final bool bien = await personaje.equipar(_comoInventario(item));
    if (!mounted) return;

    setState(() => _equipando = false);
    context.read<ColaCelebraciones>().descartar();

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            bien
                ? (reemplaza
                    ? '${item.nombre} ocupa ahora tu ${item.ranura.etiqueta.toLowerCase()}.'
                    : 'Llevas puesto: ${item.nombre}.')
                : 'No pudimos equiparlo ahora. Te espera en el Vestidor.',
          ),
        ),
      );
  }

  /// Traduce el ítem del recibo a la forma que entiende el Vestidor.
  static ItemInventario _comoInventario(ItemRecibo item) => ItemInventario(
        item: Item(
          id: item.itemId ?? item.codigoItem,
          codigo: item.codigoItem,
          nombre: item.nombre,
          ranura: item.ranura,
          rareza: item.rareza,
          origen: item.origen,
          iconoKey: item.iconoKey,
          capas: item.capas,
        ),
        itemUsuarioId: item.itemUsuarioId,
        poseido: true,
        esNuevo: true,
        motivoDesbloqueo: item.motivoDesbloqueo,
        puedeEquipar: item.puedeEquipar,
      );

  static IconData _iconoDe(RanuraItem ranura) => switch (ranura) {
        RanuraItem.cabeza => Icons.face_retouching_natural_rounded,
        RanuraItem.cuerpo => Icons.checkroom_rounded,
        RanuraItem.capa => Icons.dry_cleaning_rounded,
        RanuraItem.guantes => Icons.back_hand_rounded,
        RanuraItem.botas => Icons.hiking_rounded,
        RanuraItem.arma => Icons.hardware_rounded,
        RanuraItem.secundaria => Icons.shield_outlined,
        RanuraItem.accesorio => Icons.diamond_outlined,
        RanuraItem.mascota => Icons.pets_rounded,
        RanuraItem.montura => Icons.bedroom_baby_outlined,
      };
}
