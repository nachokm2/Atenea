/// Piezas compartidas por las pantallas de entrada al Reino (P01–P03).
///
/// Todas cumplen las reglas de accesibilidad del documento de UX: área táctil
/// de 48 dp como mínimo, la selección se marca con borde **y** con un icono de
/// verificación (el color nunca es el único portador de significado), y cada
/// control lleva su etiqueta de lector de pantalla.
library;

import 'package:flutter/material.dart';

import '../../../design/components.dart';
import '../../../design/theme.dart';
import '../../../design/tokens.dart';

/// Envoltorio seleccionable genérico: borde, tinte y sello de elegido.
class OpcionSeleccionable extends StatelessWidget {
  const OpcionSeleccionable({
    required this.seleccionada,
    required this.hijo,
    super.key,
    this.alTocar,
    this.semantica,
    this.acento,
    this.padding = const EdgeInsets.all(Espacio.sm),
    this.bloqueada = false,
  });

  final bool seleccionada;
  final Widget hijo;
  final VoidCallback? alTocar;
  final String? semantica;
  final Color? acento;
  final EdgeInsets padding;
  final bool bloqueada;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final Color color = acento ?? paleta.arcano;
    final Color borde = seleccionada ? color : paleta.borde;

    return Semantics(
      label: semantica,
      button: true,
      selected: seleccionada,
      enabled: !bloqueada && alTocar != null,
      child: ExcludeSemantics(
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: bloqueada
                ? null
                : () {
                    Tacto.seleccion(context);
                    alTocar?.call();
                  },
            borderRadius: Redondeo.rTarjeta,
            child: AnimatedContainer(
              duration: Movimiento.micro,
              curve: Movimiento.estandar,
              constraints: const BoxConstraints(
                minHeight: Medida.areaTactilMin,
                minWidth: Medida.areaTactilMin,
              ),
              padding: padding,
              decoration: BoxDecoration(
                color: seleccionada
                    ? color.withValues(alpha: 0.14)
                    : paleta.superficie,
                borderRadius: Redondeo.rTarjeta,
                border: Border.all(color: borde, width: seleccionada ? 2 : 1),
                boxShadow: seleccionada ? Sombra.brillo(color, 10) : null,
              ),
              child: Opacity(opacity: bloqueada ? 0.55 : 1, child: hijo),
            ),
          ),
        ),
      ),
    );
  }
}

/// Muestra de color (tono de piel o color de cabello).
class MuestraColor extends StatelessWidget {
  const MuestraColor({
    required this.color,
    required this.etiqueta,
    required this.seleccionada,
    required this.alTocar,
    super.key,
    this.diametro = Medida.areaTactilMin,
  });

  final Color color;
  final String etiqueta;
  final bool seleccionada;
  final VoidCallback alTocar;
  final double diametro;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Tooltip(
      message: etiqueta,
      child: Semantics(
        label: etiqueta,
        button: true,
        selected: seleccionada,
        child: ExcludeSemantics(
          child: InkWell(
            onTap: () {
              Tacto.seleccion(context);
              alTocar();
            },
            customBorder: const CircleBorder(),
            child: AnimatedContainer(
              duration: Movimiento.micro,
              curve: Movimiento.estandar,
              width: diametro,
              height: diametro,
              decoration: BoxDecoration(
                color: color,
                shape: BoxShape.circle,
                border: Border.all(
                  color: seleccionada ? paleta.arcano : paleta.borde,
                  width: seleccionada ? 3 : 1,
                ),
                boxShadow: seleccionada ? Sombra.brillo(paleta.arcano, 8) : null,
              ),
              child: seleccionada
                  ? Center(
                      child: Icon(
                        Icons.check_rounded,
                        size: 18,
                        color: paleta.sobreArcano,
                        shadows: <Shadow>[
                          Shadow(color: paleta.fondo, blurRadius: 3),
                        ],
                      ),
                    )
                  : null,
            ),
          ),
        ),
      ),
    );
  }
}

/// Píldora de texto seleccionable (rostro, oreja, estilo de cabello, trato).
class ChipOpcion extends StatelessWidget {
  const ChipOpcion({
    required this.texto,
    required this.seleccionada,
    required this.alTocar,
    super.key,
    this.icono,
    this.semantica,
  });

  final String texto;
  final bool seleccionada;
  final VoidCallback alTocar;
  final IconData? icono;
  final String? semantica;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Semantics(
      label: semantica ?? texto,
      button: true,
      selected: seleccionada,
      child: ExcludeSemantics(
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              Tacto.seleccion(context);
              alTocar();
            },
            borderRadius: Redondeo.rPildora,
            child: AnimatedContainer(
              duration: Movimiento.micro,
              curve: Movimiento.estandar,
              constraints: const BoxConstraints(minHeight: Medida.areaTactilMin),
              padding: const EdgeInsets.symmetric(
                horizontal: Espacio.md,
                vertical: Espacio.xs,
              ),
              decoration: BoxDecoration(
                color: seleccionada
                    ? paleta.arcano.withValues(alpha: 0.16)
                    : paleta.superficie,
                borderRadius: Redondeo.rPildora,
                border: Border.all(
                  color: seleccionada ? paleta.arcano : paleta.borde,
                  width: seleccionada ? 2 : 1,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  if (seleccionada)
                    Padding(
                      padding: const EdgeInsets.only(right: Espacio.xxs + 2),
                      child: Icon(
                        Icons.check_rounded,
                        size: 18,
                        color: paleta.arcano,
                      ),
                    )
                  else if (icono != null)
                    Padding(
                      padding: const EdgeInsets.only(right: Espacio.xxs + 2),
                      child: Icon(icono, size: 18, color: paleta.textoSecundario),
                    ),
                  Flexible(
                    child: Text(
                      texto,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: context.textos.bodyLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: seleccionada
                            ? paleta.textoPrimario
                            : paleta.textoSecundario,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Selector de pestañas con forma de estandartes (P03).
class SelectorPestanas extends StatelessWidget {
  const SelectorPestanas({
    required this.etiquetas,
    required this.iconos,
    required this.indice,
    required this.alCambiar,
    super.key,
  });

  final List<String> etiquetas;
  final List<IconData> iconos;
  final int indice;
  final ValueChanged<int> alCambiar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Container(
      padding: const EdgeInsets.all(Espacio.xxs),
      decoration: BoxDecoration(
        color: paleta.superficie,
        borderRadius: Redondeo.rPildora,
        border: Border.all(color: paleta.borde),
      ),
      child: Row(
        children: <Widget>[
          for (int i = 0; i < etiquetas.length; i++)
            Expanded(
              child: Semantics(
                label: etiquetas[i],
                button: true,
                selected: i == indice,
                child: ExcludeSemantics(
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () {
                        Tacto.seleccion(context);
                        alCambiar(i);
                      },
                      borderRadius: Redondeo.rPildora,
                      child: AnimatedContainer(
                        duration: Movimiento.micro,
                        curve: Movimiento.estandar,
                        height: Medida.areaTactilMin - 8,
                        decoration: BoxDecoration(
                          color: i == indice
                              ? paleta.arcano.withValues(alpha: 0.20)
                              : Colors.transparent,
                          borderRadius: Redondeo.rPildora,
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: <Widget>[
                            Icon(
                              iconos[i],
                              size: 18,
                              color: i == indice
                                  ? paleta.arcano
                                  : paleta.textoSecundario,
                            ),
                            const SizedBox(width: Espacio.xxs + 2),
                            Flexible(
                              child: Text(
                                etiquetas[i],
                                overflow: TextOverflow.ellipsis,
                                style: context.textos.bodyMedium?.copyWith(
                                  fontWeight: FontWeight.w800,
                                  color: i == indice
                                      ? paleta.textoPrimario
                                      : paleta.textoSecundario,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Aviso en línea: error del Reino, advertencia o dato útil, con una salida.
class AvisoEnLinea extends StatelessWidget {
  const AvisoEnLinea({
    required this.mensaje,
    super.key,
    this.icono = Icons.error_outline_rounded,
    this.color,
    this.textoAccion,
    this.alTocarAccion,
  });

  final String mensaje;
  final IconData icono;
  final Color? color;
  final String? textoAccion;
  final VoidCallback? alTocarAccion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final Color c = color ?? paleta.error;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(Espacio.sm),
        decoration: BoxDecoration(
          color: c.withValues(alpha: 0.12),
          borderRadius: Redondeo.rBoton,
          border: Border.all(color: c.withValues(alpha: 0.5)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Icon(icono, size: 20, color: c),
            const SizedBox(width: Espacio.xs),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    mensaje,
                    style: context.textos.bodyMedium?.copyWith(
                      color: paleta.textoPrimario,
                    ),
                  ),
                  if (textoAccion != null)
                    Padding(
                      padding: const EdgeInsets.only(top: Espacio.xxs),
                      child: InkWell(
                        onTap: alTocarAccion,
                        borderRadius: Redondeo.rChip,
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            vertical: Espacio.xs,
                            horizontal: Espacio.xxs,
                          ),
                          child: Text(
                            textoAccion!,
                            style: context.textos.labelLarge?.copyWith(color: c),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Píldora informativa que cede ante el ancho disponible.
///
/// Misma forma que la [Pildora] del sistema de diseño, pero con el texto
/// flexible: en pantallas estrechas o con el tamaño de fuente del sistema al
/// 130 % se recorta con puntos suspensivos en lugar de desbordarse.
class PildoraElastica extends StatelessWidget {
  const PildoraElastica({
    required this.texto,
    super.key,
    this.icono,
    this.color,
    this.maxLineas = 1,
  });

  final String texto;
  final IconData? icono;
  final Color? color;
  final int maxLineas;

  @override
  Widget build(BuildContext context) {
    final Color c = color ?? context.paleta.textoSecundario;
    return Semantics(
      label: texto,
      child: ExcludeSemantics(
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: Espacio.xs + 2,
            vertical: 4,
          ),
          decoration: BoxDecoration(
            color: c.withValues(alpha: 0.12),
            borderRadius: Redondeo.rPildora,
            border: Border.all(color: c.withValues(alpha: 0.35)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (icono != null) ...<Widget>[
                Icon(icono, size: 14, color: c),
                const SizedBox(width: 4),
              ],
              Flexible(
                child: Text(
                  texto,
                  maxLines: maxLineas,
                  overflow: TextOverflow.ellipsis,
                  style: context.textos.bodySmall?.copyWith(
                    color: c,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Emblema circular de Atenea para el splash y las cabeceras de entrada.
class EmblemaAtenea extends StatelessWidget {
  const EmblemaAtenea({super.key, this.tamano = 96});

  final double tamano;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Semantics(
      label: 'Atenea',
      image: true,
      child: Container(
        width: tamano,
        height: tamano,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: <Color>[
              paleta.arcano.withValues(alpha: 0.35),
              paleta.superficie,
            ],
          ),
          border: Border.all(color: paleta.oro.withValues(alpha: 0.7), width: 1.5),
          boxShadow: Sombra.brillo(paleta.arcano, 18),
        ),
        child: Center(
          child: Icon(
            Icons.auto_stories_rounded,
            size: tamano * 0.42,
            color: paleta.oro,
          ),
        ),
      ),
    );
  }
}

/// Fila de esqueletos para las rejillas de opciones mientras se preparan.
class EsqueletoOpciones extends StatelessWidget {
  const EsqueletoOpciones({super.key, this.cantidad = 6, this.alto = Medida.areaTactilMin});

  final int cantidad;
  final double alto;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: Espacio.xs,
      runSpacing: Espacio.xs,
      children: <Widget>[
        for (int i = 0; i < cantidad; i++)
          Esqueleto(alto: alto, ancho: alto + (i.isEven ? Espacio.xl : Espacio.md), radio: Redondeo.pildora),
      ],
    );
  }
}

/// Título de bloque dentro de una pestaña, más discreto que [EncabezadoSeccion].
class TituloBloque extends StatelessWidget {
  const TituloBloque({required this.texto, super.key, this.detalle});

  final String texto;
  final String? detalle;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.xs, top: Espacio.md),
      child: Row(
        children: <Widget>[
          Flexible(
            child: Text(
              texto.toUpperCase(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: context.textos.labelMedium?.copyWith(
                color: paleta.textoSecundario,
                letterSpacing: 1.1,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          if (detalle != null) ...<Widget>[
            const SizedBox(width: Espacio.xs),
            Expanded(
              child: Text(
                detalle!,
                overflow: TextOverflow.ellipsis,
                style: Cifras.pequena(context),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
