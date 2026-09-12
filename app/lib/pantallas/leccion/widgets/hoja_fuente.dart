/// Chip "Fuente" y hoja inferior con la procedencia del contenido.
///
/// Regla de producto (§8.2): **nunca se inventa una fuente**. Si el bloque no
/// tiene respaldo documental se muestra la etiqueta "Conocimiento general" y
/// la hoja lo explica sin rodeos.
library;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import '../../../navegacion/armazon.dart';

/// Chip que resume de dónde salió el contenido y abre la hoja "Fuente".
class ChipFuente extends StatelessWidget {
  const ChipFuente({required this.procedencia, super.key, this.alineado = true});

  /// Citas del bloque o de la pregunta.
  final List<Procedencia> procedencia;

  /// Ocupa el ancho disponible alineado a la izquierda.
  final bool alineado;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Procedencia? principal =
        procedencia.isEmpty ? null : procedencia.first;
    final bool delMaterial = principal?.esDelMaterial ?? false;
    final String texto =
        delMaterial ? principal!.etiqueta : 'Conocimiento general';
    final Color color = delMaterial ? p.info : p.textoSecundario;
    final IconData icono = delMaterial
        ? Icons.menu_book_rounded
        : Icons.auto_awesome_outlined;

    final Widget chip = Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: Redondeo.rPildora,
        onTap: () => mostrarHojaFuente(context, procedencia),
        child: Container(
          constraints: const BoxConstraints(minHeight: Medida.areaTactilMin),
          padding: const EdgeInsets.symmetric(horizontal: Espacio.sm),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icono, size: 16, color: color),
              const SizedBox(width: Espacio.xs),
              Flexible(
                child: Text(
                  texto,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: context.textos.bodySmall?.copyWith(
                    color: color,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: Espacio.xxs),
              Icon(Icons.chevron_right_rounded, size: 16, color: color),
            ],
          ),
        ),
      ),
    );

    final Widget conBorde = DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: Redondeo.rPildora,
        border: Border.all(color: color.withValues(alpha: 0.35)),
        color: color.withValues(alpha: 0.08),
      ),
      child: chip,
    );

    final Widget semantico = Semantics(
      button: true,
      label: 'Ver fuente: $texto',
      child: conBorde,
    );

    return alineado
        ? Align(alignment: Alignment.centerLeft, child: semantico)
        : semantico;
  }
}

/// Abre la hoja inferior con el detalle de la procedencia (§3.3 regla 4).
Future<void> mostrarHojaFuente(
  BuildContext context,
  List<Procedencia> procedencia,
) =>
    mostrarHoja<void>(
      context,
      constructor: (BuildContext hoja) => _HojaFuente(procedencia: procedencia),
    );

class _HojaFuente extends StatelessWidget {
  const _HojaFuente({required this.procedencia});

  final List<Procedencia> procedencia;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final List<Procedencia> delMaterial = procedencia
        .where((Procedencia c) => c.esDelMaterial)
        .toList(growable: false);

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          Espacio.md,
          Espacio.xs,
          Espacio.md,
          Espacio.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(Icons.menu_book_rounded, color: p.info),
                const SizedBox(width: Espacio.xs),
                Text('Fuente', style: context.textos.headlineSmall),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            if (delMaterial.isEmpty)
              _SinMaterial(p: p)
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: delMaterial.length,
                  separatorBuilder: (BuildContext contexto, int indice) =>
                      const SizedBox(height: Espacio.sm),
                  itemBuilder: (BuildContext contexto, int indice) =>
                      _FichaCita(cita: delMaterial[indice]),
                ),
              ),
            const SizedBox(height: Espacio.md),
            BotonPrimario(
              texto: 'Entendido',
              alTocar: () => Navigator.of(context).maybePop(),
            ),
          ],
        ),
      ),
    );
  }
}

class _SinMaterial extends StatelessWidget {
  const _SinMaterial({required this.p});

  final AteneaPalette p;

  @override
  Widget build(BuildContext context) {
    return TarjetaAtenea(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Pildora(
            texto: 'Conocimiento general',
            icono: Icons.auto_awesome_outlined,
          ),
          const SizedBox(height: Espacio.sm),
          Text(
            'Este paso no sale de tu material: lo compuso el Reino con '
            'conocimiento general. Lo marcamos siempre, porque nunca '
            'inventamos una cita.',
            style: context.textos.bodyLarge?.copyWith(color: p.textoSecundario),
          ),
          const SizedBox(height: Espacio.xs),
          Text(
            'Si subes más material sobre el tema, las próximas lecciones '
            'citarán tus documentos.',
            style: context.textos.bodyMedium?.copyWith(
              color: p.textoSecundario,
            ),
          ),
        ],
      ),
    );
  }
}

class _FichaCita extends StatelessWidget {
  const _FichaCita({required this.cita});

  final Procedencia cita;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String? extracto = cita.extracto;
    final String paginas = cita.referenciaPaginas;

    return TarjetaAtenea(
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(Icons.description_outlined, size: 20, color: p.info),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Text(
                  cita.tituloDocumento ?? 'Tu material',
                  style: context.textos.titleMedium,
                ),
              ),
            ],
          ),
          if (paginas.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.xxs),
            Pildora(texto: paginas, icono: Icons.bookmark_outline_rounded),
          ],
          if (extracto != null && extracto.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            Container(
              padding: const EdgeInsets.all(Espacio.sm),
              decoration: BoxDecoration(
                color: p.lectura,
                borderRadius: Redondeo.rChip,
                border: Border(left: BorderSide(color: p.info, width: 3)),
              ),
              child: Text(
                extracto,
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoPrimario,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
          ],
          const SizedBox(height: Espacio.xs),
          FilaDato(
            etiqueta: 'De tu material',
            valor: cita.tipoContenido.etiqueta,
            icono: Icons.verified_outlined,
          ),
        ],
      ),
    );
  }
}
