/// Tipografía del contenido de una lección.
///
/// El servidor envía markdown **restringido** (§7.6): párrafos, listas,
/// énfasis, código en línea y bloques cercados. Aquí se pinta sin depender de
/// ningún paquete externo, respetando la anchura de lectura, el interlineado
/// de 1,5 y los tokens de color.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../../design/tokens.dart';

/// Estilo monoespaciado para código, consultas y diagramas.
TextStyle estiloMono(BuildContext context, {double? tamano, Color? color}) =>
    GoogleFonts.robotoMono(
      fontSize: tamano ?? Tipo.secundario,
      height: 1.55,
      color: color ?? context.paleta.textoPrimario,
    );

/// Marcas en línea admitidas: **negrita**, `código` y _énfasis_.
final RegExp _enLinea = RegExp(r'\*\*(.+?)\*\*|`([^`]+)`|_(.+?)_');

/// Renderiza markdown restringido con el ritmo tipográfico del Reino.
class TextoRico extends StatelessWidget {
  const TextoRico({
    required this.texto,
    super.key,
    this.estilo,
    this.lenguajePorDefecto = 'sql',
  });

  /// Cuerpo en markdown restringido.
  final String texto;

  /// Estilo base del párrafo.
  final TextStyle? estilo;

  /// Lenguaje que se asume en los bloques cercados sin etiqueta.
  final String lenguajePorDefecto;

  @override
  Widget build(BuildContext context) {
    final TextStyle base =
        estilo ?? context.textos.bodyLarge ?? const TextStyle();
    final List<Widget> piezas = <Widget>[];
    final List<String> lineas = texto.replaceAll('\r\n', '\n').split('\n');

    final List<String> parrafo = <String>[];
    final List<String> codigo = <String>[];
    bool enCodigo = false;
    String lenguaje = lenguajePorDefecto;

    void cerrarParrafo() {
      if (parrafo.isEmpty) return;
      piezas.add(_Parrafo(texto: parrafo.join(' ').trim(), estilo: base));
      parrafo.clear();
    }

    for (final String cruda in lineas) {
      final String linea = cruda.trimRight();
      if (linea.trimLeft().startsWith('```')) {
        if (enCodigo) {
          piezas.add(
            TarjetaCodigo(codigo: codigo.join('\n'), lenguaje: lenguaje),
          );
          codigo.clear();
          enCodigo = false;
        } else {
          cerrarParrafo();
          final String etiqueta = linea.trimLeft().substring(3).trim();
          lenguaje = etiqueta.isEmpty ? lenguajePorDefecto : etiqueta;
          enCodigo = true;
        }
        continue;
      }
      if (enCodigo) {
        codigo.add(cruda);
        continue;
      }
      if (linea.trim().isEmpty) {
        cerrarParrafo();
        continue;
      }
      final String recortada = linea.trimLeft();
      if (recortada.startsWith('#')) {
        cerrarParrafo();
        piezas.add(
          Padding(
            padding: const EdgeInsets.only(top: Espacio.sm, bottom: Espacio.xxs),
            child: Text(
              recortada.replaceFirst(RegExp(r'^#+\s*'), ''),
              style: context.textos.headlineSmall,
            ),
          ),
        );
        continue;
      }
      if (recortada.startsWith('> ')) {
        cerrarParrafo();
        piezas.add(_Cita(texto: recortada.substring(2), estilo: base));
        continue;
      }
      final RegExpMatch? numerada =
          RegExp(r'^(\d+)[.)]\s+(.*)$').firstMatch(recortada);
      if (numerada != null) {
        cerrarParrafo();
        piezas.add(
          _Vineta(
            marca: '${numerada.group(1)}.',
            texto: numerada.group(2) ?? '',
            estilo: base,
          ),
        );
        continue;
      }
      if (recortada.startsWith('- ') || recortada.startsWith('* ')) {
        cerrarParrafo();
        piezas.add(
          _Vineta(marca: '•', texto: recortada.substring(2), estilo: base),
        );
        continue;
      }
      parrafo.add(recortada);
    }

    if (enCodigo && codigo.isNotEmpty) {
      piezas.add(TarjetaCodigo(codigo: codigo.join('\n'), lenguaje: lenguaje));
    }
    cerrarParrafo();

    if (piezas.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: piezas,
    );
  }

  /// Convierte las marcas en línea en fragmentos de texto enriquecido.
  static List<InlineSpan> fragmentos(
    BuildContext context,
    String texto,
    TextStyle base,
  ) {
    final AteneaPalette p = context.paleta;
    final TextStyle codigo = estiloMono(
      context,
      tamano: base.fontSize == null ? Tipo.secundario : base.fontSize! - 1,
      color: p.dominio,
    );
    final List<InlineSpan> salida = <InlineSpan>[];
    int cursor = 0;
    for (final RegExpMatch coincidencia in _enLinea.allMatches(texto)) {
      if (coincidencia.start > cursor) {
        salida.add(
          TextSpan(text: texto.substring(cursor, coincidencia.start), style: base),
        );
      }
      final String? negrita = coincidencia.group(1);
      final String? mono = coincidencia.group(2);
      final String? enfasis = coincidencia.group(3);
      if (negrita != null) {
        salida.add(
          TextSpan(
            text: negrita,
            style: base.copyWith(fontWeight: FontWeight.w800),
          ),
        );
      } else if (mono != null) {
        salida.add(TextSpan(text: mono, style: codigo));
      } else if (enfasis != null) {
        salida.add(
          TextSpan(
            text: enfasis,
            style: base.copyWith(fontStyle: FontStyle.italic),
          ),
        );
      }
      cursor = coincidencia.end;
    }
    if (cursor < texto.length) {
      salida.add(TextSpan(text: texto.substring(cursor), style: base));
    }
    return salida;
  }
}

class _Parrafo extends StatelessWidget {
  const _Parrafo({required this.texto, required this.estilo});

  final String texto;
  final TextStyle estilo;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.sm),
      child: Text.rich(
        TextSpan(children: TextoRico.fragmentos(context, texto, estilo)),
      ),
    );
  }
}

class _Vineta extends StatelessWidget {
  const _Vineta({
    required this.marca,
    required this.texto,
    required this.estilo,
  });

  final String marca;
  final String texto;
  final TextStyle estilo;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.xs, left: Espacio.xxs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: Espacio.lg,
            child: Text(
              marca,
              style: estilo.copyWith(
                color: context.paleta.arcano,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          Expanded(
            child: Text.rich(
              TextSpan(children: TextoRico.fragmentos(context, texto, estilo)),
            ),
          ),
        ],
      ),
    );
  }
}

class _Cita extends StatelessWidget {
  const _Cita({required this.texto, required this.estilo});

  final String texto;
  final TextStyle estilo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Container(
      margin: const EdgeInsets.only(bottom: Espacio.sm),
      padding: const EdgeInsets.fromLTRB(Espacio.sm, Espacio.xs, Espacio.sm, Espacio.xs),
      decoration: BoxDecoration(
        border: Border(left: BorderSide(color: p.arcano, width: 3)),
        color: p.arcano.withValues(alpha: 0.06),
      ),
      child: Text.rich(
        TextSpan(
          children: TextoRico.fragmentos(
            context,
            texto,
            estilo.copyWith(color: p.textoSecundario),
          ),
        ),
      ),
    );
  }
}

/// Bloque de código o de diagrama, con desplazamiento horizontal propio.
class TarjetaCodigo extends StatelessWidget {
  const TarjetaCodigo({
    required this.codigo,
    super.key,
    this.lenguaje,
    this.titulo,
    this.copiable = true,
  });

  /// Contenido literal.
  final String codigo;

  /// Lenguaje mostrado en la píldora superior.
  final String? lenguaje;

  /// Título alternativo a la píldora de lenguaje.
  final String? titulo;

  /// ¿Se ofrece copiar al portapapeles?
  final bool copiable;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final String etiqueta = titulo ?? (lenguaje ?? '').toUpperCase();

    return Container(
      margin: const EdgeInsets.only(bottom: Espacio.sm),
      decoration: BoxDecoration(
        color: p.lectura,
        borderRadius: Redondeo.rChip,
        border: Border.all(color: p.borde),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (etiqueta.isNotEmpty || copiable)
            Padding(
              padding: const EdgeInsets.fromLTRB(Espacio.sm, Espacio.xxs, Espacio.xxs, 0),
              child: Row(
                children: <Widget>[
                  if (etiqueta.isNotEmpty)
                    Expanded(
                      child: Text(
                        etiqueta,
                        style: context.textos.labelSmall?.copyWith(
                          color: p.textoSecundario,
                        ),
                      ),
                    )
                  else
                    const Spacer(),
                  if (copiable)
                    IconButton(
                      iconSize: 18,
                      tooltip: 'Copiar',
                      visualDensity: VisualDensity.compact,
                      constraints: const BoxConstraints(
                        minWidth: Medida.areaTactilMin,
                        minHeight: Medida.areaTactilMin,
                      ),
                      onPressed: () async {
                        await Clipboard.setData(ClipboardData(text: codigo));
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Copiado')),
                        );
                      },
                      icon: const Icon(Icons.copy_rounded),
                    ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(Espacio.sm, 0, Espacio.sm, Espacio.sm),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SelectableText(codigo, style: estiloMono(context)),
            ),
          ),
        ],
      ),
    );
  }
}
