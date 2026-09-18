/// Tarjeta de una misión (P19) y su hoja de detalle.
///
/// El botón «Reclamar» aparece **siempre que la misión está cumplida**
/// —`EstadoMision.sePuedeReclamar` es `estado == completada`, sin mirar
/// plantilla alguna—, y tocarlo es lo que dispara el cobro: cumplir no paga
/// por sí solo. El comentario anterior afirmaba justo lo contrario.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import 'formatos.dart';

/// Una misión con su progreso, su recompensa y su acción sugerida.
class TarjetaMision extends StatelessWidget {
  const TarjetaMision({
    required this.mision,
    super.key,
    this.reclamando = false,
    this.alReclamar,
    this.alTocar,
  });

  /// Misión asignada al héroe.
  final Mision mision;

  /// Se está reclamando esta misión ahora mismo.
  final bool reclamando;

  /// Reclama la recompensa, cuando la plantilla lo exige.
  final VoidCallback? alReclamar;

  /// Abre el detalle con la acción sugerida.
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool cumplida = mision.estaCumplida;
    final bool reclamable = mision.sePuedeReclamar && alReclamar != null;
    final Color acento = cumplida ? p.exito : p.arcano;

    return TarjetaAtenea(
      alTocar: alTocar,
      colorBorde: cumplida ? p.exito : null,
      semantica: '${mision.titulo}. ${mision.estado.etiqueta}. '
          'Progreso ${mision.progreso} de ${mision.meta}. '
          'Recompensa ${mision.recompensaLegible}.',
      hijo: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(
                  cumplida ? Icons.check_circle_rounded : Icons.flag_rounded,
                  color: acento,
                  size: Tipo.subtitulo,
                ),
                const SizedBox(width: Espacio.xs),
                Expanded(
                  child: Text(
                    mision.titulo,
                    style: context.textos.titleMedium,
                  ),
                ),
                if (mision.nivel != null)
                  Pildora(texto: mision.nivel!.etiqueta),
              ],
            ),
            if (mision.descripcion != null) ...<Widget>[
              const SizedBox(height: Espacio.xxs),
              Text(
                mision.descripcion!,
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ],
            const SizedBox(height: Espacio.sm),
            BarraProgreso(
              valor: mision.fraccion,
              color: acento,
              textoDerecha: cumplida
                  ? 'Cumplida'
                  : '${mision.progreso}/${mision.meta}',
            ),
            const SizedBox(height: Espacio.sm),
            Wrap(
              spacing: Espacio.xs,
              runSpacing: Espacio.xs,
              children: <Widget>[
                if (mision.recompensaXp > 0)
                  Pildora(
                    texto: '+${mision.recompensaXp} XP',
                    icono: Medallon.xp.icono,
                    color: p.oro,
                  ),
                if (mision.recompensaOro > 0)
                  Pildora(
                    texto: '+${mision.recompensaOro} Oro',
                    icono: Medallon.oro.icono,
                    color: p.oro,
                  ),
                if (mision.itemRecompensa != null)
                  Pildora(
                    texto: mision.itemRecompensa!.nombre,
                    icono: Icons.checkroom_rounded,
                    color: p.arcano,
                  ),
                if (mision.expiraEn != null &&
                    mision.ambito != AmbitoMision.diaria)
                  Pildora(
                    texto: 'Hasta el ${fechaCorta(mision.expiraEn!)}',
                    icono: Icons.event_rounded,
                  ),
              ],
            ),
            if (reclamable) ...<Widget>[
              const SizedBox(height: Espacio.md),
              BotonPrimario(
                texto: 'Reclamar recompensa',
                icono: Icons.redeem_rounded,
                cargando: reclamando,
                alTocar: alReclamar,
              ),
            ] else if (mision.estado == EstadoMision.reclamada) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              Row(
                children: <Widget>[
                  Icon(
                    Icons.verified_rounded,
                    size: Tipo.cuerpo,
                    color: p.exito,
                  ),
                  const SizedBox(width: Espacio.xxs),
                  Text(
                    'Recompensa entregada',
                    style: context.textos.bodySmall?.copyWith(color: p.exito),
                  ),
                ],
              ),
            ] else if (!cumplida && mision.accionSugerida != null) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              Row(
                children: <Widget>[
                  Icon(
                    Icons.arrow_forward_rounded,
                    size: Tipo.cuerpo,
                    color: p.arcano,
                  ),
                  const SizedBox(width: Espacio.xxs),
                  Expanded(
                    child: Text(
                      mision.accionSugerida!,
                      style: context.textos.bodySmall?.copyWith(color: p.arcano),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
