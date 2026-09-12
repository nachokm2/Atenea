/// Banner del Inicio para una ruta que el Reino está forjando (P04, estado
/// "Generando" y estado "Ruta lista").
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';

/// Aviso compacto de la generación en curso, con su progreso y su salida.
class BannerDeGeneracion extends StatelessWidget {
  const BannerDeGeneracion({
    required this.banner,
    required this.alVerGeneracion,
    required this.alAbrirRuta,
    super.key,
  });

  /// Estado que envía el panel.
  final BannerGeneracion banner;

  /// Abre P06, el estado de la forja.
  final VoidCallback alVerGeneracion;

  /// Abre P07, el mapa de la ruta.
  final VoidCallback alAbrirRuta;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String titulo = banner.titulo ?? 'tu ruta';
    final bool listo = banner.estado == EstadoTrabajo.logrado;
    final bool fallo = banner.estado == EstadoTrabajo.fallido ||
        banner.estado == EstadoTrabajo.requiereAtencion;

    final Color acento = fallo
        ? p.advertencia
        : listo
            ? p.oro
            : p.arcano;

    final IconData icono = fallo
        ? Icons.report_problem_rounded
        : listo
            ? Icons.auto_awesome_rounded
            : Icons.construction_rounded;

    final String encabezado = fallo
        ? 'La forja se detuvo'
        : listo
            ? 'Tu ruta está lista'
            : 'Construyendo $titulo';

    final String detalle = fallo
        ? banner.mensaje ?? 'Veamos qué pasó y volvamos a intentarlo.'
        : listo
            ? 'El mapa de $titulo te espera.'
            : banner.mensaje ?? 'El Reino está ordenando tu material.';

    final bool abreRuta = listo || banner.primerModuloListo;

    return TarjetaAtenea(
      colorBorde: acento,
      brillo: listo ? Rareza.legendario.brillo : null,
      alTocar: abreRuta ? alAbrirRuta : alVerGeneracion,
      semantica: '$encabezado. $detalle',
      hijo: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(icono, color: acento, size: Tipo.subtitulo),
                const SizedBox(width: Espacio.xs),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(encabezado, style: context.textos.titleMedium),
                      const SizedBox(height: 2),
                      Text(
                        detalle,
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
            if (banner.enMarcha) ...<Widget>[
              const SizedBox(height: Espacio.sm),
              BarraProgreso(
                valor: banner.fraccion,
                color: acento,
                textoDerecha: '${banner.porcentaje.round()} %',
              ),
            ],
            if (banner.primerModuloListo && !listo) ...<Widget>[
              const SizedBox(height: Espacio.sm),
              Align(
                alignment: Alignment.centerLeft,
                child: Pildora(
                  texto: 'El primer módulo ya se puede empezar',
                  icono: Icons.play_arrow_rounded,
                  color: p.exito,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
