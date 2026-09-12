/// Hojas inferiores y diálogos de la Aventura.
///
/// Regla §3.3.4 del documento de experiencia: los detalles y las decisiones
/// pequeñas (renombrar una Ruta, ver sus fuentes, entender un bloqueo, pegar
/// material) se abren como hoja inferior, nunca como pantalla nueva.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../datos/repositorios.dart';
import '../../../design/components.dart';
import '../../../design/tokens.dart';
import '../../../estado/aventura.dart';
import '../../../navegacion/armazon.dart';

/// Acciones del menú de una Ruta.
enum AccionRuta { renombrar, fuentes, archivar, desarchivar, eliminar }

/// Texto pegado como material de estudio.
class TextoPegado {
  const TextoPegado({required this.titulo, required this.texto});

  final String titulo;
  final String texto;
}

/// Cáscara común de las hojas: asa, título y contenido con aire.
class _Hoja extends StatelessWidget {
  const _Hoja({required this.titulo, required this.hijo, this.subtitulo});

  final String titulo;
  final String? subtitulo;
  final Widget hijo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            Espacio.md,
            Espacio.sm,
            Espacio.md,
            Espacio.lg,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Center(
                child: Container(
                  height: 4,
                  width: 40,
                  decoration: BoxDecoration(
                    color: p.borde,
                    borderRadius: Redondeo.rPildora,
                  ),
                ),
              ),
              const SizedBox(height: Espacio.md),
              Text(titulo, style: context.textos.headlineSmall),
              if (subtitulo != null) ...<Widget>[
                const SizedBox(height: Espacio.xxs),
                Text(
                  subtitulo!,
                  style: context.textos.bodyMedium
                      ?.copyWith(color: p.textoSecundario),
                ),
              ],
              const SizedBox(height: Espacio.md),
              hijo,
            ],
          ),
        ),
      ),
    );
  }
}

/// Menú de una Ruta: renombrar, fuentes, archivar y eliminar.
Future<AccionRuta?> menuDeRuta(
  BuildContext context, {
  required String titulo,
  required bool archivada,
  bool puedeEliminar = true,
}) {
  return mostrarHoja<AccionRuta>(
    context,
    constructor: (BuildContext hoja) {
      final AteneaPalette p = hoja.paleta;
      Widget opcion(IconData icono, String texto, AccionRuta accion,
          {Color? color}) {
        return ListTile(
          minTileHeight: Medida.areaTactilMin,
          leading: Icon(icono, color: color ?? p.textoPrimario),
          title: Text(
            texto,
            style: hoja.textos.bodyLarge?.copyWith(color: color),
          ),
          shape: const RoundedRectangleBorder(borderRadius: Redondeo.rBoton),
          onTap: () => Navigator.of(hoja).pop(accion),
        );
      }

      return _Hoja(
        titulo: titulo,
        subtitulo: 'Qué quieres hacer con esta ruta',
        hijo: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            opcion(Icons.drive_file_rename_outline_rounded, 'Renombrar la ruta',
                AccionRuta.renombrar),
            opcion(Icons.source_outlined, 'Ver el material de la ruta',
                AccionRuta.fuentes),
            if (archivada)
              opcion(Icons.unarchive_outlined, 'Devolverla a mis territorios',
                  AccionRuta.desarchivar)
            else
              opcion(Icons.archive_outlined, 'Archivar la ruta',
                  AccionRuta.archivar),
            if (puedeEliminar)
              opcion(
                Icons.delete_outline_rounded,
                'Eliminar la ruta',
                AccionRuta.eliminar,
                color: p.error,
              ),
          ],
        ),
      );
    },
  );
}

/// Pide un nombre nuevo para la Ruta.
Future<String?> pedirNuevoTitulo(
  BuildContext context, {
  required String actual,
}) {
  final TextEditingController campo = TextEditingController(text: actual);
  return mostrarHoja<String>(
    context,
    constructor: (BuildContext hoja) => _Hoja(
      titulo: 'Renombrar la ruta',
      subtitulo: 'Ponle el nombre con el que quieras recordar este territorio.',
      hijo: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          TextField(
            controller: campo,
            autofocus: true,
            textCapitalization: TextCapitalization.sentences,
            maxLength: 80,
            decoration: const InputDecoration(
              labelText: 'Nombre de la ruta',
              counterText: '',
            ),
            onSubmitted: (String valor) {
              final String limpio = valor.trim();
              if (limpio.isNotEmpty) Navigator.of(hoja).pop(limpio);
            },
          ),
          const SizedBox(height: Espacio.md),
          BotonPrimario(
            texto: 'Guardar el nombre',
            alTocar: () {
              final String limpio = campo.text.trim();
              if (limpio.isNotEmpty) Navigator.of(hoja).pop(limpio);
            },
          ),
        ],
      ),
    ),
  ).whenComplete(campo.dispose);
}

/// Pega texto como material de estudio (P05).
Future<TextoPegado?> pedirTextoPegado(BuildContext context) {
  final TextEditingController titulo = TextEditingController();
  final TextEditingController cuerpo = TextEditingController();
  return mostrarHoja<TextoPegado>(
    context,
    constructor: (BuildContext hoja) => _Hoja(
      titulo: 'Pegar material',
      subtitulo: 'Apuntes, un resumen, un artículo: el Reino leerá este texto '
          'como si fuera un documento.',
      hijo: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          TextField(
            controller: titulo,
            textCapitalization: TextCapitalization.sentences,
            maxLength: 80,
            decoration: const InputDecoration(
              labelText: 'Título del material',
              hintText: 'Apuntes de la clase 3',
              counterText: '',
            ),
          ),
          const SizedBox(height: Espacio.sm),
          TextField(
            controller: cuerpo,
            minLines: 5,
            maxLines: 10,
            decoration: const InputDecoration(
              labelText: 'Texto',
              hintText: 'Pega aquí tu material…',
            ),
          ),
          const SizedBox(height: Espacio.md),
          BotonPrimario(
            texto: 'Agregar este material',
            icono: Icons.content_paste_rounded,
            alTocar: () {
              final String t = titulo.text.trim();
              final String c = cuerpo.text.trim();
              if (c.length < 40) return;
              Navigator.of(hoja).pop(
                TextoPegado(
                  titulo: t.isEmpty ? 'Material pegado' : t,
                  texto: c,
                ),
              );
            },
          ),
          const SizedBox(height: Espacio.xs),
          Text(
            'Necesitamos al menos unas líneas para que el material sirva.',
            style: hoja.textos.bodySmall
                ?.copyWith(color: hoja.paleta.textoSecundario),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    ),
  ).whenComplete(() {
    titulo.dispose();
    cuerpo.dispose();
  });
}

/// Explica por qué un nodo está bloqueado, sin regañar.
Future<void> explicarBloqueo(
  BuildContext context, {
  required String titulo,
  required String mensaje,
  String? consejo,
}) {
  return mostrarHoja<void>(
    context,
    ajustable: false,
    constructor: (BuildContext hoja) => _Hoja(
      titulo: titulo,
      hijo: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(Icons.lock_rounded, color: hoja.paleta.textoSecundario),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Text(mensaje, style: hoja.textos.bodyLarge),
              ),
            ],
          ),
          if (consejo != null) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            Text(
              consejo,
              style: hoja.textos.bodyMedium
                  ?.copyWith(color: hoja.paleta.textoSecundario),
            ),
          ],
          const SizedBox(height: Espacio.md),
          BotonPrimario(
            texto: 'Entendido',
            alTocar: () => Navigator.of(hoja).pop(),
          ),
        ],
      ),
    ),
  );
}

/// Confirmación destructiva (eliminar una Ruta).
Future<bool> confirmarAccion(
  BuildContext context, {
  required String titulo,
  required String mensaje,
  required String textoConfirmar,
  String textoCancelar = 'Mejor no',
  bool destructiva = true,
}) async {
  final AteneaPalette p = context.paleta;
  final bool? respuesta = await showDialog<bool>(
    context: context,
    builder: (BuildContext dialogo) => AlertDialog(
      backgroundColor: p.superficieElevada,
      shape: const RoundedRectangleBorder(borderRadius: Redondeo.rTarjeta),
      title: Text(titulo),
      content: Text(mensaje),
      actions: <Widget>[
        TextButton(
          onPressed: () => Navigator.of(dialogo).pop(false),
          child: Text(textoCancelar),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogo).pop(true),
          style: destructiva
              ? TextButton.styleFrom(foregroundColor: p.error)
              : null,
          child: Text(textoConfirmar),
        ),
      ],
    ),
  );
  return respuesta ?? false;
}

/// Elige qué hacer con los temas que el material no cubre (§8.2).
Future<PoliticaCobertura?> elegirPoliticaCobertura(
  BuildContext context, {
  required PoliticaCobertura actual,
}) {
  return mostrarHoja<PoliticaCobertura>(
    context,
    constructor: (BuildContext hoja) {
      final AteneaPalette p = hoja.paleta;
      Widget opcion(
        PoliticaCobertura politica,
        IconData icono,
        String detalle,
      ) {
        final bool elegida = politica == actual;
        return Padding(
          padding: const EdgeInsets.only(bottom: Espacio.xs),
          child: TarjetaAtenea(
            alTocar: () => Navigator.of(hoja).pop(politica),
            colorBorde: elegida ? p.arcano : null,
            hijo: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(icono, color: elegida ? p.arcano : p.textoSecundario),
                const SizedBox(width: Espacio.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(politica.etiqueta, style: hoja.textos.titleMedium),
                      const SizedBox(height: 2),
                      Text(
                        detalle,
                        style: hoja.textos.bodyMedium
                            ?.copyWith(color: p.textoSecundario),
                      ),
                    ],
                  ),
                ),
                if (elegida)
                  Icon(Icons.check_circle_rounded, color: p.arcano, size: 20),
              ],
            ),
          ),
        );
      }

      return _Hoja(
        titulo: 'Tu material no cubre todo',
        subtitulo: 'Nunca inventamos una fuente. Decide qué hacer con los '
            'temas que tus documentos no alcanzan a explicar.',
        hijo: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            opcion(
              PoliticaCobertura.conocimientoDelModelo,
              Icons.auto_stories_rounded,
              'El Reino completa esos temas con su propio saber y los marca '
              'con la etiqueta "Saber del Reino".',
            ),
            opcion(
              PoliticaCobertura.soloFuente,
              Icons.fact_check_outlined,
              'La ruta se queda solo con lo que tus documentos respaldan. '
              'Será más corta, pero toda con fuente.',
            ),
            opcion(
              PoliticaCobertura.pedirMas,
              Icons.upload_file_rounded,
              'Prefieres agregar más material antes de seguir.',
            ),
          ],
        ),
      );
    },
  );
}

/// Lista del material que respalda una Ruta.
class HojaFuentes extends StatefulWidget {
  const HojaFuentes({required this.rutaId, super.key});

  final String rutaId;

  @override
  State<HojaFuentes> createState() => _HojaFuentesState();
}

class _HojaFuentesState extends State<HojaFuentes> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<ControladorAventura>().cargarFuentes(widget.rutaId);
    });
  }

  @override
  Widget build(BuildContext context) {
    final ControladorAventura aventura = context.watch<ControladorAventura>();
    final List<Documento> fuentes = aventura.fuentes;
    final AteneaPalette p = context.paleta;

    return _Hoja(
      titulo: 'Material de la ruta',
      subtitulo: 'De aquí sale lo que estudias. Cada bloque con fuente enseña '
          'de dónde viene.',
      hijo: fuentes.isEmpty
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(Icons.auto_stories_rounded, size: 36, color: p.info),
                const SizedBox(height: Espacio.sm),
                Text(
                  'Esta ruta se construyó con el saber del Reino, sin '
                  'documentos tuyos.',
                  style: context.textos.bodyLarge
                      ?.copyWith(color: p.textoSecundario),
                  textAlign: TextAlign.center,
                ),
              ],
            )
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (final Documento d in fuentes)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Espacio.xs),
                    child: TarjetaAtenea(
                      padding: const EdgeInsets.all(Espacio.sm),
                      semantica: '${d.titulo}. ${d.estado.etiqueta}.',
                      hijo: Row(
                        children: <Widget>[
                          Icon(
                            d.estaListo
                                ? Icons.description_rounded
                                : Icons.hourglass_top_rounded,
                            color: d.estaListo ? p.exito : p.info,
                          ),
                          const SizedBox(width: Espacio.sm),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(
                                  d.titulo.isEmpty
                                      ? (d.nombreArchivo ?? 'Documento')
                                      : d.titulo,
                                  style: context.textos.bodyLarge,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                Text(
                                  <String>[
                                    d.tipo.etiqueta,
                                    if (d.tamanoLegible.isNotEmpty)
                                      d.tamanoLegible,
                                    if (d.paginas != null)
                                      '${d.paginas} págs.',
                                    d.estado.etiqueta,
                                  ].join(' · '),
                                  style: context.textos.bodySmall
                                      ?.copyWith(color: p.textoSecundario),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
    );
  }
}

/// Abre la hoja con el material de una Ruta.
Future<void> mostrarFuentes(BuildContext context, String rutaId) {
  return mostrarHoja<void>(
    context,
    constructor: (BuildContext hoja) => HojaFuentes(rutaId: rutaId),
  );
}
