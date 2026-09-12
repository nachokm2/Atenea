/// Presentación de la cola de celebraciones (§5.3).
///
/// [constructorDeCelebracion] es lo que espera `CapaCelebraciones` en
/// `armazon.dart`: recibe la celebración que está al frente y devuelve el
/// overlay que le corresponde. El orden lo decide el servidor
/// (`presentation_order`), nunca esta capa.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/celebraciones.dart';
import 'marco_celebracion.dart';
import 'modal_item.dart';
import 'modal_nivel.dart';

/// Elige el overlay adecuado para la celebración visible.
///
/// Se pasa a `CapaCelebraciones(constructor: constructorDeCelebracion)`.
Widget constructorDeCelebracion(
  BuildContext context,
  Celebracion celebracion,
  VoidCallback cerrar,
) =>
    switch (celebracion.paso) {
      PasoCelebracion.subidaNivel =>
        ModalSubidaDeNivel(celebracion: celebracion),
      PasoCelebracion.item => ModalItemDesbloqueado(celebracion: celebracion),
      PasoCelebracion.racha => ModalRacha(celebracion: celebracion),
      _ => ModalGenerico(celebracion: celebracion),
    };

/// Overlay de racha: la mecánica más frecuente del Reino, y la primera de la
/// cola cuando es la primera actividad del día.
class ModalRacha extends StatelessWidget {
  const ModalRacha({required this.celebracion, super.key});

  /// Celebración de racha.
  final Celebracion celebracion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final RachaRecibo? racha = celebracion.racha;
    final HitoRacha? hito = racha?.hito;
    final bool quieto = reducirMovimiento(context);
    final int dias = racha?.actual ?? 0;

    return MarcoCelebracion(
      acento: p.brasa,
      brillo: 12,
      semantica: celebracion.semantica,
      contenido: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Center(
            child: Container(
              width: 108,
              height: 108,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: p.brasa.withValues(alpha: 0.16),
                border: Border.all(color: p.brasa, width: 2),
                boxShadow: quieto ? null : Sombra.brillo(p.brasa, 16),
              ),
              child: Icon(
                Icons.local_fire_department_rounded,
                size: 56,
                color: p.brasa,
              ),
            ),
          ),
          const SizedBox(height: Espacio.md),
          RotuloCelebracion(texto: 'Racha', color: p.textoSecundario),
          const SizedBox(height: Espacio.xxs),
          Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: <Widget>[
                CifraAnimada(
                  valor: dias,
                  estilo: Cifras.heroe(context).copyWith(color: p.brasa),
                  duracion: Movimiento.corta,
                ),
                Text(
                  dias == 1 ? ' día' : ' días',
                  style: context.textos.displaySmall,
                ),
              ],
            ),
          ),
          const SizedBox(height: Espacio.xs),
          Text(
            celebracion.detalle ?? 'La constancia forja maestría.',
            textAlign: TextAlign.center,
            style: context.textos.bodyLarge?.copyWith(color: p.textoSecundario),
          ),
          if (racha != null && racha.mejor > 0) ...<Widget>[
            const SizedBox(height: Espacio.md),
            Center(
              child: Pildora(
                texto: 'Tu mejor marca: ${racha.mejor} días',
                icono: Icons.emoji_events_outlined,
                color: p.oro,
              ),
            ),
          ],
          if (hito != null && hito.faltan > 0) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            BarraProgreso(
              valor: hito.dias <= 0
                  ? 0
                  : ((hito.dias - hito.faltan) / hito.dias)
                      .clamp(0, 1)
                      .toDouble(),
              color: p.brasa,
              etiqueta: hito.titulo ?? 'Próximo hito: ${hito.dias} días',
              textoDerecha: '${hito.faltan} para llegar',
            ),
          ],
        ],
      ),
      acciones: <Widget>[
        BotonPrimario(texto: celebracion.textoAccion, alTocar: cola.descartar),
      ],
    );
  }
}

/// Overlay de respaldo para cualquier otro paso que llegue como overlay.
class ModalGenerico extends StatelessWidget {
  const ModalGenerico({required this.celebracion, super.key});

  /// Celebración visible.
  final Celebracion celebracion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final Color acento = switch (celebracion.paso) {
      PasoCelebracion.logro => p.oro,
      PasoCelebracion.mision => p.arcano,
      PasoCelebracion.dominio => p.dominio,
      _ => p.oro,
    };

    return MarcoCelebracion(
      acento: acento,
      semantica: celebracion.semantica,
      contenido: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Center(
            child: Icon(
              switch (celebracion.paso) {
                PasoCelebracion.logro => Icons.military_tech_rounded,
                PasoCelebracion.mision => Icons.flag_rounded,
                PasoCelebracion.dominio => Medallon.dominio.icono,
                PasoCelebracion.oro => Medallon.oro.icono,
                _ => Medallon.xp.icono,
              },
              size: 56,
              color: acento,
            ),
          ),
          const SizedBox(height: Espacio.md),
          RotuloCelebracion(
            texto: celebracion.paso.etiqueta,
            color: p.textoSecundario,
          ),
          const SizedBox(height: Espacio.xxs),
          Text(
            celebracion.titulo,
            textAlign: TextAlign.center,
            style: context.textos.headlineSmall,
          ),
          if (celebracion.detalle != null) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            Text(
              celebracion.detalle!,
              textAlign: TextAlign.center,
              style: context.textos.bodyMedium?.copyWith(
                color: p.textoSecundario,
              ),
            ),
          ],
        ],
      ),
      acciones: <Widget>[
        BotonPrimario(texto: celebracion.textoAccion, alTocar: cola.descartar),
      ],
    );
  }
}
