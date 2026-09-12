/// Esqueletos de carga del grupo Inicio, Misiones, Logros y notificaciones.
///
/// Toda carga de más de 300 ms se cubre con esqueletos, nunca con la pantalla
/// en blanco (§6.1). El latido se apaga cuando el sistema pide reducir
/// movimiento.
library;

import 'package:flutter/material.dart';

import '../../../design/components.dart';
import '../../../design/tokens.dart';

/// Da un latido suave a los esqueletos.
class PulsoEsqueleto extends StatefulWidget {
  const PulsoEsqueleto({required this.hijo, super.key});

  /// Bloque de esqueletos a animar.
  final Widget hijo;

  @override
  State<PulsoEsqueleto> createState() => _PulsoEsqueletoState();
}

class _PulsoEsqueletoState extends State<PulsoEsqueleto>
    with SingleTickerProviderStateMixin {
  late final AnimationController _control = AnimationController(
    vsync: this,
    duration: Movimiento.celebracion,
  );

  @override
  void initState() {
    super.initState();
    _control.repeat(reverse: true);
  }

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (reducirMovimiento(context)) {
      return ExcludeSemantics(child: widget.hijo);
    }
    return ExcludeSemantics(
      child: FadeTransition(
        opacity: Tween<double>(begin: 0.45, end: 1).animate(
          CurvedAnimation(parent: _control, curve: Curves.easeInOut),
        ),
        child: widget.hijo,
      ),
    );
  }
}

/// Tarjeta de esqueleto genérica: unas cuantas barras dentro de una tarjeta.
class TarjetaEsqueleto extends StatelessWidget {
  const TarjetaEsqueleto({
    super.key,
    this.lineas = 3,
    this.conMedallon = false,
    this.alto,
  });

  /// Cuántas barras de texto simular.
  final int lineas;

  /// Añade un círculo a la izquierda.
  final bool conMedallon;

  /// Alto fijo opcional (para rejillas).
  final double? alto;

  @override
  Widget build(BuildContext context) {
    final Widget columna = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (int i = 0; i < lineas; i++) ...<Widget>[
          if (i > 0) const SizedBox(height: Espacio.xs),
          Esqueleto(
            alto: i == 0 ? Tipo.subtitulo : Tipo.secundario,
            ancho: i == 0 ? null : (i.isEven ? Medida.lecturaMax / 3 : null),
          ),
        ],
      ],
    );

    return TarjetaAtenea(
      hijo: SizedBox(
        height: alto,
        child: conMedallon
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const Esqueleto(
                    alto: Medida.areaTactilMin - Espacio.xs,
                    ancho: Medida.areaTactilMin - Espacio.xs,
                    radio: Redondeo.pildora,
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(child: columna),
                ],
              )
            : columna,
      ),
    );
  }
}

/// Lista de tarjetas de esqueleto, para Misiones y notificaciones.
class ListaEsqueleto extends StatelessWidget {
  const ListaEsqueleto({
    super.key,
    this.filas = 3,
    this.lineas = 3,
    this.conMedallon = true,
  });

  /// Cuántas tarjetas pintar.
  final int filas;

  /// Barras por tarjeta.
  final int lineas;

  /// Círculo a la izquierda de cada tarjeta.
  final bool conMedallon;

  @override
  Widget build(BuildContext context) {
    return PulsoEsqueleto(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          for (int i = 0; i < filas; i++) ...<Widget>[
            if (i > 0) const SizedBox(height: Espacio.sm),
            TarjetaEsqueleto(lineas: lineas, conMedallon: conMedallon),
          ],
        ],
      ),
    );
  }
}

/// Esqueleto completo del Inicio, con la forma real de sus bloques.
class EsqueletoInicio extends StatelessWidget {
  const EsqueletoInicio({super.key});

  @override
  Widget build(BuildContext context) {
    return PulsoEsqueleto(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const Esqueleto(alto: Tipo.titulo, ancho: Medida.lecturaMax / 2),
          const SizedBox(height: Espacio.md),
          const TarjetaEsqueleto(lineas: 4, conMedallon: true),
          const SizedBox(height: Espacio.md),
          const TarjetaEsqueleto(lineas: 3),
          const SizedBox(height: Espacio.md),
          const TarjetaEsqueleto(lineas: 4),
          const SizedBox(height: Espacio.lg),
          const Esqueleto(alto: Tipo.subtitulo, ancho: Medida.lecturaMax / 3),
          const SizedBox(height: Espacio.sm),
          const TarjetaEsqueleto(lineas: 2, conMedallon: true),
          const SizedBox(height: Espacio.sm),
          const TarjetaEsqueleto(lineas: 2, conMedallon: true),
          const SizedBox(height: Espacio.lg),
          Row(
            children: const <Widget>[
              Expanded(child: TarjetaEsqueleto(lineas: 2)),
              SizedBox(width: Espacio.sm),
              Expanded(child: TarjetaEsqueleto(lineas: 2)),
              SizedBox(width: Espacio.sm),
              Expanded(child: TarjetaEsqueleto(lineas: 2)),
            ],
          ),
        ],
      ),
    );
  }
}
