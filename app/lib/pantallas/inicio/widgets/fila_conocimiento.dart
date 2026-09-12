/// Fila de "Tus conocimientos" en el Inicio (P04): un conocimiento con su
/// dominio, calculado siempre por el servidor.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import 'formatos.dart';

/// Un conocimiento con su emblema, su dominio y su estado.
class FilaConocimiento extends StatelessWidget {
  const FilaConocimiento({required this.area, super.key, this.alTocar});

  /// Conocimiento con nivel, dominio y estado.
  final AreaConocimiento area;

  /// Lleva al mapa de la Ruta o al Territorio.
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final double fraccion = (area.dominio / 100).clamp(0, 1).toDouble();
    final bool pideRepaso = area.estado.pideRepaso;
    final Color acento = pideRepaso ? p.advertencia : p.dominio;

    return TarjetaAtenea(
      alTocar: alTocar,
      padding: const EdgeInsets.all(Espacio.sm),
      semantica: '${area.nombre}. Dominio ${porcentaje(fraccion)}. '
          '${area.estado.etiqueta}.',
      hijo: ExcludeSemantics(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            Container(
              width: Medida.areaTactilMin - Espacio.xs,
              height: Medida.areaTactilMin - Espacio.xs,
              decoration: BoxDecoration(
                color: acento.withValues(alpha: 0.16),
                shape: BoxShape.circle,
                border: Border.all(color: acento.withValues(alpha: 0.5)),
              ),
              alignment: Alignment.center,
              child: Text(
                _inicial(area),
                style: context.textos.titleMedium?.copyWith(color: acento),
              ),
            ),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          area.nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: context.textos.titleMedium,
                        ),
                      ),
                      if (pideRepaso)
                        Pildora(
                          texto: area.estado.etiqueta,
                          icono: Icons.refresh_rounded,
                          color: p.advertencia,
                        ),
                    ],
                  ),
                  const SizedBox(height: Espacio.xxs + 2),
                  BarraProgreso(
                    valor: fraccion,
                    color: acento,
                    textoDerecha: porcentaje(fraccion),
                    alto: Espacio.xs,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  static String _inicial(AreaConocimiento area) {
    final String base = area.nombreCorto.isNotEmpty ? area.nombreCorto : area.nombre;
    if (base.isEmpty) return '?';
    return base.substring(0, 1).toUpperCase();
  }
}
