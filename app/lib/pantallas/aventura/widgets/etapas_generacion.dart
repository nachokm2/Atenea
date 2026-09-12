/// Las etapas con nombre de P06.
///
/// Principio de la pantalla: **nunca una barra vacía**. Si el Reino manda sus
/// propias etapas se muestran tal cual; si solo manda los trabajos, se usan sus
/// etiquetas; y si todavía no hay nada, se dibuja el recorrido canónico de la
/// forja para que la espera tenga forma desde el primer segundo.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';

/// Estado visible de una etapa de la forja.
enum EstadoEtapa { pendiente, enCurso, hecha, fallida }

/// Una etapa tal como se pinta en la lista de P06.
class EtapaVisible {
  const EtapaVisible({
    required this.titulo,
    required this.estado,
    this.detalle,
  });

  /// Nombre de la etapa ("Leyendo tus documentos").
  final String titulo;

  /// Cómo va.
  final EstadoEtapa estado;

  /// Dato real que hace tolerable la espera ("14 conceptos clave").
  final String? detalle;
}

/// Recorrido canónico de la forja, según el documento de experiencia.
const List<String> _recorridoCanonico = <String>[
  'Leyendo tus documentos',
  'Extrayendo los conceptos clave',
  'Diseñando los módulos',
  'Escribiendo el primer módulo',
  'Completando la ruta',
];

/// Umbral de avance en el que empieza cada etapa canónica.
const List<double> _umbrales = <double>[0, 20, 40, 60, 85];

EstadoEtapa _desdeTrabajo(EstadoTrabajo estado) => switch (estado) {
      EstadoTrabajo.logrado => EstadoEtapa.hecha,
      EstadoTrabajo.ejecutando => EstadoEtapa.enCurso,
      EstadoTrabajo.fallido ||
      EstadoTrabajo.cancelado ||
      EstadoTrabajo.requiereAtencion =>
        EstadoEtapa.fallida,
      EstadoTrabajo.pendiente => EstadoEtapa.pendiente,
    };

/// Traduce el estado de la generación a la lista de etapas que verá el usuario.
List<EtapaVisible> etapasVisibles(EstadoGeneracion? generacion) {
  final EstadoGeneracion? g = generacion;

  if (g != null && g.etapas.isNotEmpty) {
    return <EtapaVisible>[
      for (final EtapaGeneracion e in g.etapas)
        EtapaVisible(
          titulo: e.titulo.isEmpty ? 'Forjando' : e.titulo,
          estado: _desdeTrabajo(e.estado),
          detalle: e.detalle,
        ),
    ];
  }

  if (g != null && g.trabajos.isNotEmpty) {
    return <EtapaVisible>[
      for (final Trabajo t in g.trabajos)
        EtapaVisible(
          titulo: t.tipo.etiqueta,
          estado: _desdeTrabajo(t.estado),
          detalle: t.etiqueta,
        ),
    ];
  }

  // Recorrido canónico: el avance global decide dónde está la forja.
  final double avance = (g?.porcentaje ?? 0).clamp(0, 100).toDouble();
  int actual = 0;
  for (int i = 0; i < _umbrales.length; i++) {
    if (avance >= _umbrales[i]) actual = i;
  }
  final bool termino = g?.termino ?? false;
  final bool fallo = g?.fallo ?? false;

  return <EtapaVisible>[
    for (int i = 0; i < _recorridoCanonico.length; i++)
      EtapaVisible(
        titulo: _recorridoCanonico[i],
        estado: termino
            ? EstadoEtapa.hecha
            : i < actual
                ? EstadoEtapa.hecha
                : i == actual
                    ? (fallo ? EstadoEtapa.fallida : EstadoEtapa.enCurso)
                    : EstadoEtapa.pendiente,
        detalle: i == actual ? g?.etapa : null,
      ),
  ];
}

/// Lista de etapas con su marca, su nombre y su dato real.
class ListaEtapas extends StatelessWidget {
  const ListaEtapas({required this.etapas, super.key});

  final List<EtapaVisible> etapas;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (int i = 0; i < etapas.length; i++)
          _FilaEtapa(
            etapa: etapas[i],
            posicion: i + 1,
            total: etapas.length,
            ultima: i == etapas.length - 1,
          ),
      ],
    );
  }
}

class _FilaEtapa extends StatelessWidget {
  const _FilaEtapa({
    required this.etapa,
    required this.posicion,
    required this.total,
    required this.ultima,
  });

  final EtapaVisible etapa;
  final int posicion;
  final int total;
  final bool ultima;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final (Color color, IconData icono, String lectura) = switch (etapa.estado) {
      EstadoEtapa.hecha => (p.exito, Icons.check_rounded, 'lista'),
      EstadoEtapa.enCurso => (p.arcano, Icons.bolt_rounded, 'en marcha'),
      EstadoEtapa.fallida => (p.error, Icons.close_rounded, 'detenida'),
      EstadoEtapa.pendiente => (
          p.textoSecundario,
          Icons.circle_outlined,
          'en espera',
        ),
    };
    final bool enCurso = etapa.estado == EstadoEtapa.enCurso;

    return Semantics(
      label: 'Etapa $posicion de $total, ${etapa.titulo}, $lectura',
      child: ExcludeSemantics(
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Column(
                children: <Widget>[
                  _Marca(color: color, icono: icono, enCurso: enCurso),
                  if (!ultima)
                    Expanded(
                      child: Container(
                        width: 2,
                        margin: const EdgeInsets.symmetric(vertical: 2),
                        color: etapa.estado == EstadoEtapa.hecha
                            ? p.exito.withValues(alpha: 0.45)
                            : p.borde,
                      ),
                    ),
                ],
              ),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.only(bottom: ultima ? 0 : Espacio.sm),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        etapa.titulo,
                        style: enCurso
                            ? context.textos.titleMedium
                            : context.textos.bodyLarge?.copyWith(
                                color: etapa.estado == EstadoEtapa.pendiente
                                    ? p.textoSecundario
                                    : p.textoPrimario,
                              ),
                      ),
                      if (etapa.detalle != null &&
                          etapa.detalle!.trim().isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            etapa.detalle!,
                            style: context.textos.bodyMedium
                                ?.copyWith(color: p.textoSecundario),
                          ),
                        ),
                    ],
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

class _Marca extends StatelessWidget {
  const _Marca({
    required this.color,
    required this.icono,
    required this.enCurso,
  });

  final Color color;
  final IconData icono;
  final bool enCurso;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool quieto = reducirMovimiento(context);
    return SizedBox(
      height: 26,
      width: 26,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          if (enCurso && !quieto)
            SizedBox(
              height: 26,
              width: 26,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(
                  color.withValues(alpha: 0.7),
                ),
              ),
            ),
          Container(
            height: 22,
            width: 22,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: 0.16),
              border: Border.all(color: color.withValues(alpha: 0.8), width: 1.4),
            ),
            child: Icon(icono, size: 13, color: color),
          ),
          if (enCurso && quieto)
            Positioned(
              bottom: 0,
              child: Container(
                height: 3,
                width: 10,
                decoration: BoxDecoration(
                  color: p.arcano,
                  borderRadius: Redondeo.rPildora,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
