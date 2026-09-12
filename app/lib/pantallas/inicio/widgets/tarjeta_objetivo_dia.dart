/// Tarjeta "Misión de hoy" del Inicio (P04): el objetivo diario con su
/// progreso y el atajo a las Misiones (P19).
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';

/// Objetivo del día con barra de progreso y resumen de misiones.
class TarjetaObjetivoDia extends StatelessWidget {
  const TarjetaObjetivoDia({
    required this.objetivo,
    required this.misiones,
    required this.alVerMisiones,
    super.key,
  });

  /// Objetivo diario vigente, resuelto por el servidor.
  final ObjetivoDiario objetivo;

  /// Misiones resumidas que envía el panel.
  final List<Mision> misiones;

  /// Abre P19.
  final VoidCallback alVerMisiones;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool cumplido = objetivo.cumplido;
    final Color acento = cumplido ? p.exito : p.arcano;
    final int cumplidas =
        misiones.where((Mision m) => m.estaCumplida).length;

    return TarjetaAtenea(
      alTocar: alVerMisiones,
      colorBorde: cumplido ? p.exito : null,
      semantica: cumplido
          ? 'Misión de hoy cumplida. ${_meta(objetivo)}.'
          : 'Misión de hoy: ${_meta(objetivo)}. '
              'Llevas ${objetivo.progreso} de ${objetivo.meta}.',
      hijo: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Text(
                  'MISIÓN DE HOY',
                  style: context.textos.labelMedium?.copyWith(
                    color: p.textoSecundario,
                    letterSpacing: 1.2,
                  ),
                ),
                const Spacer(),
                Text(
                  'Ver misiones',
                  style: context.textos.bodySmall?.copyWith(color: p.arcano),
                ),
                Icon(
                  Icons.chevron_right_rounded,
                  color: p.arcano,
                  size: Tipo.cuerpo,
                ),
              ],
            ),
            const SizedBox(height: Espacio.xs),
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: <Widget>[
                Icon(
                  cumplido ? Icons.check_circle_rounded : Icons.flag_rounded,
                  color: acento,
                  size: Tipo.titulo,
                ),
                const SizedBox(width: Espacio.xs),
                Expanded(
                  child: Text(
                    cumplido ? 'Objetivo cumplido' : _meta(objetivo),
                    style: Cifras.media(context),
                  ),
                ),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            BarraProgreso(
              valor: objetivo.fraccion,
              color: acento,
              textoDerecha: '${objetivo.progreso}/${objetivo.meta}',
            ),
            const SizedBox(height: Espacio.xs),
            Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    cumplido
                        ? _textoCumplido(objetivo)
                        : 'Te faltan ${objetivo.restante} ${objetivo.tipo.unidad}.',
                    style: context.textos.bodyMedium?.copyWith(
                      color: p.textoSecundario,
                    ),
                  ),
                ),
                if (misiones.isNotEmpty)
                  Pildora(
                    texto: '$cumplidas/${misiones.length} misiones',
                    icono: Icons.task_alt_rounded,
                    color: cumplidas == misiones.length ? p.exito : p.textoSecundario,
                  ),
              ],
            ),
            if (objetivo.tieneCambioPendiente) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              Text(
                'Mañana cambia a ${objetivo.metaPendiente ?? objetivo.meta} '
                '${(objetivo.tipoPendiente ?? objetivo.tipo).unidad}.',
                style: context.textos.bodySmall?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  static String _meta(ObjetivoDiario objetivo) => switch (objetivo.tipo) {
        TipoObjetivo.minutos => 'Estudia ${objetivo.meta} minutos',
        TipoObjetivo.actividades => 'Completa ${objetivo.meta} actividades',
        TipoObjetivo.xp => 'Gana ${objetivo.meta} XP',
      };

  static String _textoCumplido(ObjetivoDiario objetivo) => objetivo.oroBonus > 0
      ? 'El Reino te premió con ${objetivo.oroBonus} de oro.'
      : 'Hoy ya cumpliste. Todo lo que sigue es ventaja.';
}
