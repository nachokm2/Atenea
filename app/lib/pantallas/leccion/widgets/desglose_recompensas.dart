/// Presentación del `RewardsReceipt` (§7.10) en P10 y P12.
///
/// La app **no calcula nada**: cada cifra que aparece aquí viene ya resuelta
/// por el servidor. Lo único que se decide en el cliente es el ritmo con el
/// que se revela, y siempre existe la versión estática para quien pide
/// reducir movimiento.
library;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';
import '../../../estado/celebraciones.dart';

/// Desglose en filas: XP de la actividad, XP de las respuestas, oro y dominio.
class DesgloseRecompensas extends StatelessWidget {
  const DesgloseRecompensas({
    required this.recibo,
    super.key,
    this.etiquetaActividad = 'Lección',
    this.respuestas,
  });

  /// Recibo canónico devuelto por el servidor.
  final ReciboRecompensas recibo;

  /// Nombre de la fila principal ("Lección" o "Desafío del módulo").
  final String etiquetaActividad;

  /// Cuántas preguntas se respondieron, para la segunda fila.
  final int? respuestas;

  @override
  Widget build(BuildContext context) {
    final XpRecibo? xp = recibo.xp;
    final OroRecibo? oro = recibo.oro;
    final DeltaDominio? dominio = recibo.dominioDelTema;
    final ConocimientoRecibo? saber = recibo.conocimiento;

    final List<Widget> filas = <Widget>[];

    if (xp != null && xp.xpActividad > 0) {
      filas.add(
        FilaRecompensa(
          medallon: Medallon.xp,
          etiqueta: etiquetaActividad,
          valor: xp.xpActividad,
          sufijo: ' XP',
        ),
      );
    }
    if (xp != null && xp.xpPreguntas > 0) {
      final int total = respuestas ?? 0;
      filas.add(
        FilaRecompensa(
          medallon: Medallon.xp,
          etiqueta: total > 0 ? '$total respuestas' : 'Respuestas',
          valor: xp.xpPreguntas,
          sufijo: ' XP',
        ),
      );
    }
    if (xp != null &&
        xp.hayAlgo &&
        xp.xpActividad == 0 &&
        xp.xpPreguntas == 0) {
      filas.add(
        FilaRecompensa(
          medallon: Medallon.xp,
          etiqueta: 'Experiencia',
          valor: xp.cantidad,
          sufijo: ' XP',
        ),
      );
    }
    if (oro != null && oro.hayAlgo) {
      filas.add(
        FilaRecompensa(
          medallon: Medallon.oro,
          etiqueta: 'Oro',
          valor: oro.cantidad,
          nota: 'Saldo: ${oro.saldoDespues}',
        ),
      );
    }

    if (filas.isEmpty && dominio == null && saber == null) {
      return const SizedBox.shrink();
    }

    return TarjetaAtenea(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          for (int i = 0; i < filas.length; i++)
            _Escalonado(indice: i, hijo: filas[i]),
          if (dominio != null)
            _Escalonado(
              indice: filas.length,
              hijo: FilaDominio(
                nombre: dominio.nombre,
                antes: dominio.antes,
                despues: dominio.despues,
                estado: dominio.estado.etiqueta,
              ),
            )
          else if (saber != null && saber.delta != 0)
            _Escalonado(
              indice: filas.length,
              hijo: FilaDominio(
                nombre: saber.nombre,
                antes: saber.dominioAntes,
                despues: saber.dominioDespues,
                estado: saber.estado.etiqueta,
              ),
            ),
          if ((xp?.multiplicador ?? 1) != 1) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            Text(
              '${xp!.motivoLegible}: el Reino aplicó un ajuste a la '
              'experiencia de esta actividad.',
              style: context.textos.bodySmall?.copyWith(
                color: context.paleta.textoSecundario,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Aparición escalonada de cada fila, con versión estática.
class _Escalonado extends StatelessWidget {
  const _Escalonado({required this.indice, required this.hijo});

  final int indice;
  final Widget hijo;

  @override
  Widget build(BuildContext context) {
    if (reducirMovimiento(context)) return hijo;
    return hijo
        .animate(delay: Movimiento.micro * indice)
        .fadeIn(duration: Movimiento.corta)
        .slideY(begin: 0.25, end: 0, curve: Movimiento.estandar);
  }
}

/// Una línea del desglose: medallón, concepto y cifra que cuenta.
class FilaRecompensa extends StatelessWidget {
  const FilaRecompensa({
    required this.medallon,
    required this.etiqueta,
    required this.valor,
    super.key,
    this.sufijo = '',
    this.nota,
  });

  /// Medallón de juego que identifica el concepto.
  final Medallon medallon;

  /// Concepto ("Lección", "3 respuestas", "Oro").
  final String etiqueta;

  /// Cantidad otorgada, tal como la envió el servidor.
  final int valor;

  /// Unidad que acompaña a la cifra (" XP").
  final String sufijo;

  /// Aclaración secundaria ("Saldo: 320").
  final String? nota;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Semantics(
      label: '$etiqueta: más $valor$sufijo',
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Espacio.xs),
        child: Row(
          children: <Widget>[
            Icon(medallon.icono, size: 20, color: medallon.color(context)),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(etiqueta, style: context.textos.bodyLarge),
                  if (nota != null)
                    Text(
                      nota!,
                      style: context.textos.bodySmall?.copyWith(
                        color: p.textoSecundario,
                      ),
                    ),
                ],
              ),
            ),
            ExcludeSemantics(
              child: CifraAnimada(
                valor: valor,
                prefijo: '+',
                sufijo: sufijo,
                estilo: Cifras.media(context).copyWith(
                  color: medallon.color(context),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Variación de dominio de un tema o conocimiento ("31 % → 34 %").
class FilaDominio extends StatelessWidget {
  const FilaDominio({
    required this.nombre,
    required this.antes,
    required this.despues,
    super.key,
    this.estado,
  });

  /// Nombre del tema o del conocimiento.
  final String nombre;

  /// Dominio antes de la actividad, en porcentaje.
  final double antes;

  /// Dominio después, en porcentaje.
  final double despues;

  /// Estado de dominio resultante.
  final String? estado;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Semantics(
      label: 'Dominio de $nombre: de ${antes.round()} por ciento a '
          '${despues.round()} por ciento',
      child: Padding(
        padding: const EdgeInsets.only(top: Espacio.xs),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(Medallon.dominio.icono, size: 20, color: p.dominio),
                const SizedBox(width: Espacio.sm),
                Expanded(
                  child: Text(
                    'Dominio $nombre',
                    style: context.textos.bodyLarge,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                ExcludeSemantics(
                  child: Text(
                    '${antes.round()} % → ${despues.round()} %',
                    style: Cifras.pequena(context).copyWith(color: p.dominio),
                  ),
                ),
              ],
            ),
            const SizedBox(height: Espacio.xs),
            BarraProgreso(
              valor: (despues / 100).clamp(0, 1).toDouble(),
              color: p.dominio,
            ),
            if (estado != null) ...<Widget>[
              const SizedBox(height: Espacio.xxs),
              Align(
                alignment: Alignment.centerLeft,
                child: Pildora(texto: estado!, color: p.dominio),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Barra de experiencia global con el nivel y lo que falta para el siguiente.
class BarraNivel extends StatelessWidget {
  const BarraNivel({required this.nivel, super.key, this.xpTotal});

  /// Bloque `level` del recibo.
  final NivelRecibo? nivel;

  /// XP total tras la acción, para el lector de pantalla.
  final int? xpTotal;

  @override
  Widget build(BuildContext context) {
    final NivelRecibo? n = nivel;
    if (n == null) return const SizedBox.shrink();
    final AteneaPalette p = context.paleta;
    final String rango = n.tituloRangoDespues ?? '';

    return TarjetaAtenea(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Medallon.nivel.icono, size: 20, color: p.arcano),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Text(
                  rango.isEmpty ? 'Nivel ${n.despues}' : 'Nivel ${n.despues} · $rango',
                  style: context.textos.titleMedium,
                ),
              ),
              if (xpTotal != null)
                Text(
                  '$xpTotal XP',
                  style: Cifras.pequena(context).copyWith(color: p.oro),
                ),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          BarraProgreso(
            valor: n.fraccion,
            color: p.oro,
            textoDerecha: n.xpParaSiguiente > 0
                ? '${n.xpParaSiguiente} XP para el nivel ${n.despues + 1}'
                : null,
          ),
        ],
      ),
    );
  }
}

/// Chips de los eventos secundarios del recibo (misiones, logros, extras).
class ChipsCelebracion extends StatelessWidget {
  const ChipsCelebracion({required this.chips, super.key});

  /// Celebraciones que la cola dejó en formato chip.
  final List<Celebracion> chips;

  @override
  Widget build(BuildContext context) {
    final List<Celebracion> visibles = chips
        .where(
          (Celebracion c) =>
              c.paso == PasoCelebracion.mision ||
              c.paso == PasoCelebracion.logro ||
              c.paso == PasoCelebracion.item,
        )
        .toList(growable: false);
    if (visibles.isEmpty) return const SizedBox.shrink();

    final AteneaPalette p = context.paleta;
    return Wrap(
      spacing: Espacio.xs,
      runSpacing: Espacio.xs,
      children: <Widget>[
        for (final Celebracion c in visibles)
          _ChipEvento(
            texto: c.titulo,
            detalle: c.detalle,
            color: switch (c.paso) {
              PasoCelebracion.mision => p.arcano,
              PasoCelebracion.logro => p.oro,
              _ => c.rarezaVisual.color,
            },
            icono: switch (c.paso) {
              PasoCelebracion.mision => Icons.flag_rounded,
              PasoCelebracion.logro => Icons.military_tech_rounded,
              _ => Icons.shield_moon_rounded,
            },
          ),
      ],
    );
  }
}

class _ChipEvento extends StatelessWidget {
  const _ChipEvento({
    required this.texto,
    required this.color,
    required this.icono,
    this.detalle,
  });

  final String texto;
  final String? detalle;
  final Color color;
  final IconData icono;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: detalle == null ? texto : '$texto. $detalle',
      child: Container(
        constraints: const BoxConstraints(minHeight: Medida.areaTactilMin),
        padding: const EdgeInsets.symmetric(
          horizontal: Espacio.sm,
          vertical: Espacio.xs,
        ),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: Redondeo.rPildora,
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icono, size: 18, color: color),
            const SizedBox(width: Espacio.xs),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  texto,
                  style: context.textos.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                    color: color,
                  ),
                ),
                if (detalle != null)
                  Text(
                    detalle!,
                    style: context.textos.bodySmall?.copyWith(
                      color: context.paleta.textoSecundario,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Módulos, territorios o desafíos que la acción dejó abiertos.
class ListaDesbloqueos extends StatelessWidget {
  const ListaDesbloqueos({required this.desbloqueos, super.key});

  /// Sección `unlocks` del recibo.
  final List<Desbloqueo> desbloqueos;

  @override
  Widget build(BuildContext context) {
    if (desbloqueos.isEmpty) return const SizedBox.shrink();
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      colorBorde: p.oro,
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(Icons.lock_open_rounded, size: 20, color: p.oro),
              const SizedBox(width: Espacio.xs),
              Text('Se abrió camino', style: context.textos.titleMedium),
            ],
          ),
          const SizedBox(height: Espacio.xs),
          for (final Desbloqueo d in desbloqueos)
            Padding(
              padding: const EdgeInsets.only(top: Espacio.xxs),
              child: Text(
                '${d.tipo.etiqueta}: ${d.nombre}',
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Aviso discreto cuando alguna recompensa quedó reintentándose.
class AvisoSincronizacion extends StatelessWidget {
  const AvisoSincronizacion({super.key});

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Container(
      padding: const EdgeInsets.all(Espacio.sm),
      decoration: BoxDecoration(
        color: p.info.withValues(alpha: 0.10),
        borderRadius: Redondeo.rChip,
        border: Border.all(color: p.info.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: <Widget>[
          Icon(Icons.cloud_sync_outlined, size: 20, color: p.info),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Text(
              'Tu avance está guardado. Algunas recompensas terminan de '
              'confirmarse en un momento.',
              style: context.textos.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }
}
