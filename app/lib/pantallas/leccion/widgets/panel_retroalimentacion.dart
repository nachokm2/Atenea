/// Panel de retroalimentación de P09.
///
/// Sube desde abajo en cuanto el Reino corrige la respuesta. Enseña con el
/// error: nunca resta, nunca regaña y siempre ofrece la explicación, la
/// respuesta correcta y la fuente.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';
import 'hoja_fuente.dart';
import 'texto_rico.dart';

/// Veredicto de una respuesta, con su explicación y su salida.
class PanelRetroalimentacion extends StatelessWidget {
  const PanelRetroalimentacion({
    required this.resultado,
    required this.textoContinuar,
    required this.alContinuar,
    super.key,
    this.alReexplicar,
    this.reexplicando = false,
  });

  /// Corrección que devolvió el servidor.
  final ResultadoRespuesta resultado;

  /// Texto del botón principal ("Continuar" o "Terminar la lección").
  final String textoContinuar;

  /// Avanza al siguiente paso.
  final VoidCallback alContinuar;

  /// Pide otra explicación del tema ("No lo entiendo").
  final VoidCallback? alReexplicar;

  /// La re-explicación está en camino.
  final bool reexplicando;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final _Veredicto v = _Veredicto.de(resultado, p);
    final bool quieto = reducirMovimiento(context);
    final String? explicacion = resultado.explicacion;
    final String? comentario = resultado.retroalimentacion;
    final String? sandbox = resultado.salidaSandbox;
    final String correcta = resultado.respuestaCorrectaTexto;

    final Widget panel = Container(
      decoration: BoxDecoration(
        color: p.superficieElevada,
        borderRadius: Redondeo.rHoja,
        border: Border(top: BorderSide(color: v.color, width: 3)),
        boxShadow: Sombra.hoja(Theme.of(context).brightness),
      ),
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        Espacio.sm,
        Espacio.md,
        Espacio.sm,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(v.icono, color: v.color),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Text(
                  v.titulo,
                  style: context.textos.headlineSmall?.copyWith(color: v.color),
                ),
              ),
              if (resultado.xpOtorgado > 0)
                Semantics(
                  label: '${resultado.xpOtorgado} puntos de experiencia',
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Icon(
                        Medallon.xp.icono,
                        size: 18,
                        color: p.oro,
                      ),
                      const SizedBox(width: Espacio.xxs),
                      Text(
                        '+${resultado.xpOtorgado} XP',
                        style: Cifras.pequena(context).copyWith(color: p.oro),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          if (v.subtitulo != null) ...<Widget>[
            const SizedBox(height: Espacio.xxs),
            Text(
              v.subtitulo!,
              style: context.textos.bodyMedium?.copyWith(
                color: p.textoSecundario,
              ),
            ),
          ],
          if (!resultado.esCorrecta && correcta.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            Container(
              padding: const EdgeInsets.all(Espacio.sm),
              decoration: BoxDecoration(
                color: p.exito.withValues(alpha: 0.10),
                borderRadius: Redondeo.rChip,
                border: Border.all(color: p.exito.withValues(alpha: 0.5)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(Icons.check_circle_rounded, size: 18, color: p.exito),
                  const SizedBox(width: Espacio.xs),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'La respuesta correcta',
                          style: context.textos.labelSmall?.copyWith(
                            color: p.exito,
                          ),
                        ),
                        Text(correcta, style: context.textos.bodyLarge),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (explicacion != null && explicacion.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 220),
              child: SingleChildScrollView(
                child: TextoRico(texto: explicacion),
              ),
            ),
          ],
          if (comentario != null && comentario.isNotEmpty) ...<Widget>[
            Text(
              comentario,
              style: context.textos.bodyMedium?.copyWith(
                color: p.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.xs),
          ],
          if (sandbox != null && sandbox.isNotEmpty)
            TarjetaCodigo(
              codigo: sandbox,
              titulo: 'RESULTADO DE TU CONSULTA',
              copiable: false,
            ),
          const SizedBox(height: Espacio.xs),
          Row(
            children: <Widget>[
              if (resultado.procedencia.isNotEmpty)
                Flexible(
                  child: ChipFuente(
                    procedencia: resultado.procedencia,
                    alineado: false,
                  ),
                ),
              if (alReexplicar != null) ...<Widget>[
                const SizedBox(width: Espacio.xs),
                Flexible(
                  child: TextButton.icon(
                    onPressed: reexplicando ? null : alReexplicar,
                    icon: reexplicando
                        ? const SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.lightbulb_outline_rounded, size: 18),
                    label: const Text('No lo entiendo'),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: Espacio.xxs),
          BotonPrimario(texto: textoContinuar, alTocar: alContinuar),
        ],
      ),
    );

    final Widget conSemantica = Semantics(
      liveRegion: true,
      label: '${v.titulo}. ${v.subtitulo ?? ''}',
      child: panel,
    );

    if (quieto) return conSemantica;
    return TweenAnimationBuilder<double>(
      key: ValueKey<String>('panel-${resultado.preguntaId ?? v.titulo}'),
      tween: Tween<double>(begin: 1, end: 0),
      duration: Movimiento.corta,
      curve: Movimiento.estandar,
      builder: (BuildContext contexto, double t, Widget? hijo) =>
          Transform.translate(
        offset: Offset(0, t * Espacio.xxl),
        child: Opacity(opacity: 1 - t, child: hijo),
      ),
      child: conSemantica,
    );
  }
}

/// Titular, color e icono del veredicto.
class _Veredicto {
  const _Veredicto({
    required this.titulo,
    required this.color,
    required this.icono,
    this.subtitulo,
  });

  final String titulo;
  final String? subtitulo;
  final Color color;
  final IconData icono;

  /// El copy sigue el tono del Reino: celebra el acierto y acompaña el error.
  static _Veredicto de(ResultadoRespuesta r, AteneaPalette p) {
    if (r.estaPendiente) {
      return _Veredicto(
        titulo: 'Respuesta guardada',
        subtitulo:
            'La estamos revisando con calma. Te avisamos en Inicio cuando '
            'tenga veredicto; mientras tanto, sigue adelante.',
        color: p.info,
        icono: Icons.hourglass_bottom_rounded,
      );
    }
    if (r.esCorrecta) {
      return _Veredicto(
        titulo: 'Correcto',
        subtitulo: r.metodo == MetodoEvaluacion.sandbox
            ? 'Tu consulta devolvió lo que pedía el ejercicio.'
            : null,
        color: p.exito,
        icono: Icons.check_circle_rounded,
      );
    }
    if (r.esParcial) {
      return _Veredicto(
        titulo: 'Casi',
        subtitulo:
            'Vas por buen camino: ${r.puntajeParcial.round()} % de la respuesta '
            'era correcta.',
        color: p.dominio,
        icono: Icons.trending_up_rounded,
      );
    }
    return _Veredicto(
      titulo: 'Aún no',
      subtitulo: 'Mira por qué; así se aprende de verdad.',
      color: p.advertencia,
      icono: Icons.info_rounded,
    );
  }
}
