/// Los nodos del camino de P07.
///
/// El mapa es una senda vertical: un riel continuo a la izquierda y, colgando
/// de él, los nodos grandes de los módulos, los pequeños de las lecciones, el
/// escudo del Desafío del módulo y, al final, el tesoro de la Ruta.
///
/// El bloqueo se muestra siempre con candado **y** con la frase del requisito:
/// el color nunca es el único portador de significado.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import 'comunes_aventura.dart';

/// Cómo se pinta un nodo del camino.
enum EstiloNodo {
  /// Ya superado.
  completado,

  /// Donde está el usuario ahora mismo: late.
  actual,

  /// Abierto, todavía sin empezar.
  disponible,

  /// Pide completar algo antes.
  bloqueado,

  /// El Reino todavía está escribiendo su contenido.
  enConstruccion,
}

/// Color semántico del estilo de nodo.
Color colorDeNodo(BuildContext context, EstiloNodo estilo) {
  final AteneaPalette p = context.paleta;
  return switch (estilo) {
    EstiloNodo.completado => p.exito,
    EstiloNodo.actual => p.arcano,
    EstiloNodo.disponible => p.dominio,
    EstiloNodo.bloqueado => p.textoSecundario,
    EstiloNodo.enConstruccion => p.info,
  };
}

/// Icono que acompaña a cada estilo.
IconData iconoDeNodo(EstiloNodo estilo) => switch (estilo) {
      EstiloNodo.completado => Icons.check_rounded,
      EstiloNodo.actual => Icons.play_arrow_rounded,
      EstiloNodo.disponible => Icons.play_arrow_rounded,
      EstiloNodo.bloqueado => Icons.lock_rounded,
      EstiloNodo.enConstruccion => Icons.local_fire_department_rounded,
    };

/// Nombre del estado para el lector de pantalla.
String etiquetaDeNodo(EstiloNodo estilo) => switch (estilo) {
      EstiloNodo.completado => 'Completado',
      EstiloNodo.actual => 'Estás aquí',
      EstiloNodo.disponible => 'Disponible',
      EstiloNodo.bloqueado => 'Bloqueado',
      EstiloNodo.enConstruccion => 'En construcción',
    };

/// Un eslabón del camino: el riel con su nodo y el contenido a la derecha.
class NodoCamino extends StatelessWidget {
  const NodoCamino({
    required this.hijo,
    required this.estilo,
    super.key,
    this.icono,
    this.grande = false,
    this.lineaArriba = true,
    this.lineaAbajo = true,
    this.tramoSuperiorHecho = false,
    this.tramoInferiorHecho = false,
    this.sangria = 0,
  });

  /// Contenido a la derecha del riel.
  final Widget hijo;

  final EstiloNodo estilo;

  /// Icono del nodo; por defecto, el de su estilo.
  final IconData? icono;

  /// Los módulos llevan nodo grande; las lecciones, pequeño.
  final bool grande;

  final bool lineaArriba;
  final bool lineaAbajo;

  /// Pinta en verde el tramo ya recorrido del camino.
  final bool tramoSuperiorHecho;
  final bool tramoInferiorHecho;

  /// Sangría del contenido (las lecciones cuelgan de su módulo).
  final double sangria;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = colorDeNodo(context, estilo);
    final double diametro = grande ? 44 : 26;
    final Color hecho = p.exito.withValues(alpha: 0.45);

    final Widget circulo = Container(
      height: diametro,
      width: diametro,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: estilo == EstiloNodo.bloqueado
            ? p.superficie
            : color.withValues(alpha: 0.18),
        border: Border.all(color: color, width: grande ? 2.4 : 1.8),
      ),
      child: Icon(
        icono ?? iconoDeNodo(estilo),
        size: grande ? 22 : 14,
        color: color,
      ),
    );

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: 48,
            child: Column(
              children: <Widget>[
                SizedBox(
                  height: grande ? Espacio.xs : Espacio.sm,
                  child: lineaArriba
                      ? Container(
                          width: 2,
                          color: tramoSuperiorHecho ? hecho : p.borde,
                        )
                      : null,
                ),
                if (estilo == EstiloNodo.actual)
                  PulsoSuave(color: color, hijo: circulo)
                else
                  circulo,
                Expanded(
                  child: lineaAbajo
                      ? Container(
                          width: 2,
                          color: tramoInferiorHecho ? hecho : p.borde,
                        )
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(left: sangria, bottom: Espacio.sm),
              child: hijo,
            ),
          ),
        ],
      ),
    );
  }
}

/// Tarjeta de un módulo en el mapa.
class ContenidoModulo extends StatelessWidget {
  const ContenidoModulo({
    required this.modulo,
    required this.estilo,
    required this.expandido,
    required this.alTocar,
    super.key,
  });

  final ModuloRuta modulo;
  final EstiloNodo estilo;
  final bool expandido;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = colorDeNodo(context, estilo);
    final bool bloqueado = estilo == EstiloNodo.bloqueado;
    final bool conocimientoGeneral =
        modulo.temas.any((Tema t) => t.esConocimientoGeneral);

    return TarjetaAtenea(
      alTocar: alTocar,
      elevada: estilo == EstiloNodo.actual,
      colorBorde: estilo == EstiloNodo.actual ? color.withValues(alpha: 0.7) : null,
      brillo: estilo == EstiloNodo.actual ? 10 : null,
      semantica: 'Módulo ${modulo.posicion}: ${modulo.nombreVisible}. '
          '${etiquetaDeNodo(estilo)}. '
          '${modulo.leccionesCompletadas} de ${modulo.leccionesTotales} '
          'lecciones.',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Módulo ${modulo.posicion}',
                      style: context.textos.labelSmall
                          ?.copyWith(color: p.textoSecundario),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      modulo.nombreVisible,
                      style: context.textos.titleLarge?.copyWith(
                        color: bloqueado ? p.textoSecundario : p.textoPrimario,
                      ),
                    ),
                  ],
                ),
              ),
              if (modulo.estrellas > 0) Estrellas(cantidad: modulo.estrellas),
              const SizedBox(width: Espacio.xxs),
              AnimatedRotation(
                turns: expandido ? 0.5 : 0,
                duration: Movimiento.corta,
                child: Icon(
                  Icons.expand_more_rounded,
                  color: p.textoSecundario,
                ),
              ),
            ],
          ),
          if (modulo.resumen != null && modulo.resumen!.trim().isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.xxs),
            Text(
              modulo.resumen!,
              style: context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          const SizedBox(height: Espacio.xs),
          Wrap(
            spacing: Espacio.xs,
            runSpacing: Espacio.xxs,
            children: <Widget>[
              Pildora(
                texto: etiquetaDeNodo(estilo),
                icono: iconoDeNodo(estilo),
                color: color,
              ),
              if (duracionLegible(modulo.minutosEstimados).isNotEmpty)
                Pildora(
                  texto: duracionLegible(modulo.minutosEstimados),
                  icono: Icons.hourglass_bottom_rounded,
                  color: p.textoSecundario,
                ),
              if (conocimientoGeneral)
                Pildora(
                  texto: 'Saber del Reino',
                  icono: Icons.auto_stories_rounded,
                  color: p.info,
                ),
            ],
          ),
          if (bloqueado) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(Icons.lock_rounded, size: 15, color: p.textoSecundario),
                const SizedBox(width: Espacio.xxs + 2),
                Expanded(
                  child: Text(
                    modulo.motivoBloqueo ??
                        'Completa el módulo anterior para abrir esta zona.',
                    style: context.textos.bodyMedium
                        ?.copyWith(color: p.textoSecundario),
                  ),
                ),
              ],
            ),
          ] else ...<Widget>[
            const SizedBox(height: Espacio.sm),
            BarraProgreso(
              valor: modulo.leccionesTotales == 0
                  ? 0
                  : modulo.leccionesCompletadas / modulo.leccionesTotales,
              color: color,
              etiqueta:
                  'Lecciones ${modulo.leccionesCompletadas}/${modulo.leccionesTotales}',
              textoDerecha: porcentajeLegible(modulo.dominio),
            ),
          ],
        ],
      ),
    );
  }
}

/// Fila compacta de una lección colgando de su módulo.
class ContenidoLeccion extends StatelessWidget {
  const ContenidoLeccion({
    required this.leccion,
    required this.estilo,
    required this.alTocar,
    super.key,
  });

  final ResumenLeccion leccion;
  final EstiloNodo estilo;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = colorDeNodo(context, estilo);
    final int minutos = (leccion.segundosEstimados / 60).round();
    final bool bloqueado = estilo == EstiloNodo.bloqueado;

    return TarjetaAtenea(
      alTocar: alTocar,
      padding: const EdgeInsets.symmetric(
        horizontal: Espacio.sm,
        vertical: Espacio.sm,
      ),
      colorBorde: estilo == EstiloNodo.actual ? color.withValues(alpha: 0.6) : null,
      semantica: '${leccion.titulo}. ${etiquetaDeNodo(estilo)}. '
          '$minutos minutos.',
      hijo: Row(
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  leccion.titulo.isEmpty
                      ? 'Lección ${leccion.posicion}'
                      : leccion.titulo,
                  style: context.textos.bodyLarge?.copyWith(
                    fontWeight: estilo == EstiloNodo.actual
                        ? FontWeight.w800
                        : FontWeight.w600,
                    color: bloqueado ? p.textoSecundario : p.textoPrimario,
                  ),
                ),
                const SizedBox(height: Espacio.xxs),
                Wrap(
                  spacing: Espacio.xs,
                  runSpacing: Espacio.xxs,
                  children: <Widget>[
                    Pildora(
                      texto: '$minutos min',
                      icono: Icons.hourglass_bottom_rounded,
                      color: p.textoSecundario,
                    ),
                    if (estilo == EstiloNodo.enConstruccion)
                      Pildora(
                        texto: 'Forjándose',
                        icono: Icons.local_fire_department_rounded,
                        color: p.info,
                      ),
                    if (leccion.esRepaso)
                      Pildora(
                        texto: 'Repaso',
                        icono: Icons.replay_rounded,
                        color: p.dominio,
                      ),
                    if (leccion.contenidoEscaso)
                      Pildora(
                        texto: 'Material escaso',
                        icono: Icons.info_outline_rounded,
                        color: p.advertencia,
                      ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: Espacio.xs),
          Icon(
            estilo == EstiloNodo.completado
                ? Icons.check_circle_rounded
                : (bloqueado
                    ? Icons.lock_rounded
                    : Icons.chevron_right_rounded),
            color: color,
            size: 20,
          ),
        ],
      ),
    );
  }
}

/// Nodo del Desafío del módulo: el escudo al final de cada zona.
class ContenidoDesafio extends StatelessWidget {
  const ContenidoDesafio({
    required this.evaluacion,
    required this.estilo,
    required this.alTocar,
    super.key,
  });

  final ResumenEvaluacion evaluacion;
  final EstiloNodo estilo;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = evaluacion.aprobada ? p.oro : colorDeNodo(context, estilo);
    final bool bloqueado = estilo == EstiloNodo.bloqueado;

    return TarjetaAtenea(
      alTocar: alTocar,
      colorBorde: color.withValues(alpha: bloqueado ? 0.3 : 0.6),
      brillo: evaluacion.aprobada ? 10 : null,
      // El rótulo sale del servidor, no de una constante. El contrato lo
      // exige dos veces: `title` es «Nombre narrativo (no usar la palabra
      // "Desafío")» —CONTRACT.md línea 1383— y la decisión D12 fija el nombre
      // visible en «Prueba del módulo» / «Prueba del Castillo», porque
      // «desafío» ya nombra otra actividad, `challenge`, que paga recompensas
      // distintas. Este nodo no se pintaba nunca, así que la infracción no se
      // veía hasta que empezó a llegar el dato.
      semantica: '${evaluacion.titulo}. ${etiquetaDeNodo(estilo)}. '
          '${evaluacion.preguntas} preguntas.',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Icons.shield_rounded, color: color, size: 22),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Text(
                  evaluacion.titulo,
                  style: context.textos.titleMedium,
                ),
              ),
              if (evaluacion.aprobada)
                Icon(Icons.verified_rounded, color: p.oro, size: 20),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          Wrap(
            spacing: Espacio.xs,
            runSpacing: Espacio.xxs,
            children: <Widget>[
              Pildora(
                texto: '${evaluacion.preguntas} preguntas',
                icono: Icons.quiz_outlined,
                color: p.textoSecundario,
              ),
              Pildora(
                texto: 'Se supera con ${evaluacion.puntajeAprobacion.round()} %',
                icono: Icons.flag_rounded,
                color: p.textoSecundario,
              ),
              if (evaluacion.mejorPuntaje != null)
                Pildora(
                  texto: 'Tu mejor marca: ${evaluacion.mejorPuntaje!.round()} %',
                  icono: Icons.emoji_events_rounded,
                  color: p.oro,
                ),
            ],
          ),
          if (bloqueado || evaluacion.enEnfriamiento) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            Text(
              // Tres razones distintas, tres mensajes. Antes eran dos, y quien
              // había gastado sus intentos del día leía «completa las
              // lecciones» sobre unas lecciones ya completadas.
              evaluacion.enEnfriamiento
                  ? 'Vuelve en un rato: el Reino prepara preguntas nuevas para '
                      'tu siguiente intento.'
                  : evaluacion.sinIntentosHoy
                      ? 'Hoy ya usaste tus '
                          '${evaluacion.intentosMaximosPorDia} intentos. '
                          'Mañana vuelves a tenerlos.'
                      : 'Completa las lecciones del módulo para presentarte a '
                          'la prueba.',
              style: context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
            ),
          ],
        ],
      ),
    );
  }
}

/// Nodo del Reto opcional del módulo: unas pocas preguntas de todo lo
/// aprendido, tras completarlo.
///
/// Distinto del Desafío (`ContenidoDesafio`, arriba): ese es la evaluación
/// del módulo, con aprobación y reprobación; el Reto es opcional, sin
/// castigo, y paga otra recompensa (`CHALLENGE_COMPLETED`, D12). El servidor
/// no manda ningún campo que diga si ya se agotó
/// (`content.challenges_per_module_max`): este nodo se ofrece siempre que el
/// módulo está completo, y quien ya lo hizo se entera al tocarlo, por el
/// mensaje que trae el `409 CHALLENGE_ALREADY_USED`.
class ContenidoReto extends StatelessWidget {
  const ContenidoReto({required this.alTocar, super.key});

  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;

    return TarjetaAtenea(
      alTocar: alTocar,
      colorBorde: p.arcano.withValues(alpha: 0.5),
      semantica: 'Reto del módulo, opcional. Preguntas de todo lo que '
          'aprendiste aquí, más difíciles.',
      hijo: Row(
        children: <Widget>[
          Icon(Icons.military_tech_rounded, color: p.arcano, size: 22),
          const SizedBox(width: Espacio.xs),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Reto del módulo', style: context.textos.titleMedium),
                Text(
                  'Opcional: preguntas de todo lo que aprendiste aquí, más '
                  'difíciles.',
                  style: context.textos.bodyMedium
                      ?.copyWith(color: p.textoSecundario),
                ),
              ],
            ),
          ),
          Icon(Icons.chevron_right_rounded, color: p.textoSecundario),
        ],
      ),
    );
  }
}

/// Tesoro del final del camino: el ítem de conocimiento de la Ruta.
class ContenidoTesoro extends StatelessWidget {
  const ContenidoTesoro({
    required this.completada,
    super.key,
    this.item,
  });

  final bool completada;
  final Item? item;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Item? premio = item;
    final Rareza rareza = premio == null
        ? Rareza.raro
        : Rareza.desdeApi(premio.rareza.api);
    final Color color = completada ? rareza.color : p.textoSecundario;

    return TarjetaAtenea(
      colorBorde: color.withValues(alpha: completada ? 0.75 : 0.35),
      brillo: completada ? rareza.brillo : null,
      elevada: completada,
      semantica: completada
          ? 'Ruta completada. Ganaste ${premio?.nombre ?? 'el tesoro de la ruta'}.'
          : 'Tesoro de la ruta, todavía en silueta.',
      hijo: Stack(
        children: <Widget>[
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Container(
                    height: 48,
                    width: 48,
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: completada ? 0.18 : 0.08),
                      borderRadius: Redondeo.rTarjeta,
                      border: Border.all(color: color.withValues(alpha: 0.5)),
                    ),
                    child: Icon(
                      completada
                          ? Icons.workspace_premium_rounded
                          : Icons.help_outline_rounded,
                      color: color.withValues(alpha: completada ? 1 : 0.5),
                    ),
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          completada
                              ? (premio?.nombre ?? 'Tesoro de la Ruta')
                              : 'Tesoro por reclamar',
                          style: context.textos.titleMedium,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          completada
                              ? 'La Ruta es tuya. El territorio queda marcado en '
                                  'tu mapa.'
                              : 'Completa todos los módulos para descubrir qué '
                                  'guarda el final del camino.',
                          style: context.textos.bodyMedium
                              ?.copyWith(color: p.textoSecundario),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              if (premio != null) ...<Widget>[
                const SizedBox(height: Espacio.sm),
                Row(
                  children: <Widget>[
                    ChipRareza(rareza: rareza),
                    const SizedBox(width: Espacio.xs),
                    Pildora(
                      texto: 'Se gana aprendiendo',
                      icono: Icons.school_rounded,
                      color: p.dominio,
                    ),
                  ],
                ),
              ],
            ],
          ),
          if (completada)
            Positioned(
              right: 0,
              top: 0,
              child: Transform.rotate(
                angle: math.pi / 2,
                child: OrnamentoEsquina(color: rareza.color),
              ),
            ),
        ],
      ),
    );
  }
}
