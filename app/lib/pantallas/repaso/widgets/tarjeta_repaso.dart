/// Tarjeta de una sugerencia de repaso: tema, motivo y cuánto tarda.
///
/// Compartida entre el resultado del Desafío (P12, que ya la usaba como
/// widget privado) y la lista de repasos recomendados: es la misma promesa
/// ("esto se te está olvidando, repásalo") en dos sitios donde puede llegar.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';

class TarjetaRepaso extends StatelessWidget {
  const TarjetaRepaso({required this.sugerencia, required this.alTocar, super.key});

  final SugerenciaRepaso sugerencia;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.xs),
      child: TarjetaAtenea(
        alTocar: alTocar,
        colorBorde: sugerencia.esUrgente ? p.advertencia : null,
        hijo: Row(
          children: <Widget>[
            Icon(Icons.refresh_rounded, color: p.dominio),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(sugerencia.titulo, style: context.textos.titleMedium),
                  Text(
                    sugerencia.motivo ??
                        '${sugerencia.preguntas} preguntas · '
                            '${sugerencia.minutosEstimados} min',
                    style: context.textos.bodyMedium?.copyWith(
                      color: p.textoSecundario,
                    ),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: p.textoSecundario),
          ],
        ),
      ),
    );
  }
}
