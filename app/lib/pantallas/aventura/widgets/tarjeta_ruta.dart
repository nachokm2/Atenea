/// Tarjetas de Ruta de P22: mis territorios, las Rutas del Reino y el
/// esqueleto que ocupa su lugar mientras el Reino responde.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import 'comunes_aventura.dart';

/// Tarjeta de una Ruta propia: emblema, avance y estado.
///
/// Todas las cifras (módulos, lecciones, dominio, porcentaje) llegan resueltas
/// desde el Reino; aquí solo se visten.
class TarjetaRuta extends StatelessWidget {
  const TarjetaRuta({
    required this.ruta,
    required this.alTocar,
    super.key,
    this.alAbrirMenu,
    this.indice = 0,
  });

  final ResumenRuta ruta;
  final VoidCallback alTocar;
  final VoidCallback? alAbrirMenu;
  final int indice;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool forjando = ruta.estaGenerando;
    final bool completada = ruta.estado == EstadoRuta.completada;
    final Color acento = colorDesdeHex(ruta.colorAcento) ?? p.arcano;
    final Color colorEstado = colorDeEstadoRuta(context, ruta.estado);

    final String subtitulo = ruta.nombreConocimiento?.trim().isNotEmpty ?? false
        ? ruta.nombreConocimiento!
        : (ruta.objetivo ?? ruta.resumen ?? '');

    final String resumenLector = forjando
        ? '${ruta.titulo}. El Reino está forjando esta ruta.'
        : '${ruta.titulo}. ${ruta.modulosCompletados} de ${ruta.modulos} '
            'módulos. Dominio ${ruta.dominio.round()} por ciento.';

    return AparecerEnCascada(
      indice: indice,
      hijo: TarjetaAtenea(
        alTocar: alTocar,
        semantica: resumenLector,
        colorBorde: completada ? p.oro.withValues(alpha: 0.55) : null,
        brillo: completada ? 8 : null,
        hijo: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                EmblemaTerritorio(
                  nombre: ruta.nombreConocimiento ?? ruta.titulo,
                  iconoKey: ruta.iconoKey,
                  colorAcento: ruta.colorAcento,
                  resplandor: completada,
                ),
                const SizedBox(width: Espacio.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        ruta.titulo.isEmpty ? 'Ruta sin nombre' : ruta.titulo,
                        style: context.textos.titleLarge,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      if (subtitulo.isNotEmpty) ...<Widget>[
                        const SizedBox(height: 2),
                        Text(
                          subtitulo,
                          style: context.textos.bodyMedium
                              ?.copyWith(color: p.textoSecundario),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ],
                  ),
                ),
                if (alAbrirMenu != null)
                  IconButton(
                    onPressed: alAbrirMenu,
                    icon: const Icon(Icons.more_horiz_rounded),
                    tooltip: 'Opciones de la ruta',
                  ),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            Wrap(
              spacing: Espacio.xs,
              runSpacing: Espacio.xxs,
              children: <Widget>[
                Pildora(
                  texto: ruta.estado.etiqueta,
                  icono: iconoDeEstadoRuta(ruta.estado),
                  color: colorEstado,
                ),
                if (ruta.modoFuente == ModoFuente.sinFuente)
                  Pildora(
                    texto: 'Saber del Reino',
                    icono: Icons.auto_stories_rounded,
                    color: p.info,
                  ),
                if (ruta.esDelReino)
                  Pildora(
                    texto: 'Ruta del Reino',
                    icono: Icons.shield_moon_rounded,
                    color: p.dominio,
                  ),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            if (forjando)
              _FranjaForja(acento: acento)
            else ...<Widget>[
              BarraProgreso(
                valor: ruta.porcentajeAvance / 100,
                color: completada ? p.oro : acento,
                etiqueta: ruta.modulos > 0
                    ? 'Módulos ${ruta.modulosCompletados}/${ruta.modulos}'
                    : 'Avance de la ruta',
                textoDerecha: porcentajeLegible(ruta.porcentajeAvance),
              ),
              const SizedBox(height: Espacio.sm),
              Row(
                children: <Widget>[
                  FichaMedallon(
                    tipo: Medallon.dominio,
                    valor: porcentajeLegible(ruta.dominio),
                    etiqueta: 'Dominio',
                    compacto: true,
                  ),
                  const SizedBox(width: Espacio.md),
                  FichaMedallon(
                    tipo: Medallon.xp,
                    valor:
                        '${ruta.leccionesCompletadas}/${ruta.leccionesTotales}',
                    etiqueta: 'Lecciones completadas',
                    compacto: true,
                  ),
                  if (duracionLegible(ruta.minutosEstimados).isNotEmpty) ...<Widget>[
                    const SizedBox(width: Espacio.md),
                    FichaMedallon(
                      tipo: Medallon.tiempo,
                      valor: duracionLegible(ruta.minutosEstimados),
                      etiqueta: 'Duración estimada',
                      compacto: true,
                    ),
                  ],
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Franja de la Ruta que todavía se está forjando.
class _FranjaForja extends StatelessWidget {
  const _FranjaForja({required this.acento});

  final Color acento;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool quieto = reducirMovimiento(context);
    return Row(
      children: <Widget>[
        Expanded(
          child: ClipRRect(
            borderRadius: Redondeo.rPildora,
            child: SizedBox(
              height: 10,
              child: LinearProgressIndicator(
                value: quieto ? 0.35 : null,
                backgroundColor: p.borde,
                valueColor: AlwaysStoppedAnimation<Color>(acento),
              ),
            ),
          ),
        ),
        const SizedBox(width: Espacio.sm),
        Text(
          'Toca para ver el avance',
          style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
        ),
      ],
    );
  }
}

/// Tarjeta de una Ruta del Reino: curada, pregenerada y lista para empezar.
class TarjetaRutaDelReino extends StatelessWidget {
  const TarjetaRutaDelReino({
    required this.ruta,
    required this.alTocar,
    required this.alEmpezar,
    super.key,
    this.adoptando = false,
    this.indice = 0,
  });

  final ResumenRuta ruta;
  final VoidCallback alTocar;
  final VoidCallback alEmpezar;
  final bool adoptando;
  final int indice;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String duracion = duracionLegible(ruta.minutosEstimados);

    return AparecerEnCascada(
      indice: indice,
      hijo: TarjetaAtenea(
        alTocar: alTocar,
        semantica: '${ruta.titulo}. Ruta del Reino. '
            '${ruta.modulos} módulos${duracion.isEmpty ? '' : ', $duracion'}.',
        hijo: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                EmblemaTerritorio(
                  nombre: ruta.nombreConocimiento ?? ruta.titulo,
                  iconoKey: ruta.iconoKey,
                  colorAcento: ruta.colorAcento,
                  tamano: 46,
                ),
                const SizedBox(width: Espacio.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        ruta.titulo,
                        style: context.textos.titleMedium,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        ruta.resumen ??
                            ruta.objetivo ??
                            'Un camino ya trazado por el Reino.',
                        style: context.textos.bodySmall
                            ?.copyWith(color: p.textoSecundario),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            Wrap(
              spacing: Espacio.xs,
              runSpacing: Espacio.xxs,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                if (ruta.modulos > 0)
                  Pildora(
                    texto: '${ruta.modulos} módulos',
                    icono: Icons.view_module_rounded,
                    color: p.textoSecundario,
                  ),
                if (duracion.isNotEmpty)
                  Pildora(
                    texto: duracion,
                    icono: Icons.hourglass_bottom_rounded,
                    color: p.textoSecundario,
                  ),
                Pildora(
                  texto: ruta.nivelDeclarado.etiqueta,
                  icono: Icons.signal_cellular_alt_rounded,
                  color: p.dominio,
                ),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            SizedBox(
              width: double.infinity,
              child: FilledButton.tonalIcon(
                onPressed: adoptando ? null : alEmpezar,
                icon: adoptando
                    ? const SizedBox(
                        height: 16,
                        width: 16,
                        child: CircularProgressIndicator(strokeWidth: 2.2),
                      )
                    : const Icon(Icons.play_arrow_rounded),
                label: Text(adoptando ? 'Preparando…' : 'Empezar esta ruta'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Esqueleto de una tarjeta de Ruta mientras el Reino responde.
class EsqueletoRuta extends StatelessWidget {
  const EsqueletoRuta({super.key});

  @override
  Widget build(BuildContext context) {
    return TarjetaAtenea(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Esqueleto(alto: 52, ancho: 52, radio: Redondeo.tarjeta),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const Esqueleto(alto: 18, ancho: 180),
                    const SizedBox(height: Espacio.xs),
                    Esqueleto(alto: 12, ancho: 120, radio: Redondeo.chip),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: Espacio.md),
          const Esqueleto(alto: 10, radio: Redondeo.pildora),
          const SizedBox(height: Espacio.sm),
          const Esqueleto(alto: 12, ancho: 200),
        ],
      ),
    );
  }
}
