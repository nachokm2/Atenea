/// Chip "Fuente" y hoja inferior con la procedencia del contenido.
///
/// Regla de producto (§8.2): **nunca se inventa una fuente**. Si el bloque no
/// tiene respaldo documental se muestra la etiqueta "Conocimiento general" y
/// la hoja lo explica sin rodeos.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

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

/// La hoja "Fuente".
///
/// Es la única pieza que puede citar de verdad: `Procedencia` (`ProvenanceOut`,
/// §7.6) solo trae el `chunk_id` que respalda el contenido, y a propósito —
/// mandar el título, las páginas y el texto de cada cita en **toda** respuesta
/// de lección multiplicaría el peso de la carga por el número de citas, la
/// inmensa mayoría de las cuales nadie llega a abrir. El documento, las
/// páginas y el fragmento en sí viven en `GET /chunks/{id}`
/// (CONTRACT.md:3088), y por eso existían enteros y sin usar:
/// `RepoDocumentos.fragmento`, el DTO `Fragmento` y hasta el propio endpoint.
/// Faltaba esta llamada.
///
/// Sin ella, la ficha de cada cita se quedaba con los campos que
/// `Procedencia` nunca lleva —título, páginas, extracto—, así que el botón que
/// existe precisamente para que el aprendiz compruebe que el Reino no se
/// inventa nada abría una ficha vacía: "Tu material" a secas, sin una sola
/// palabra citada.
class _HojaFuente extends StatefulWidget {
  const _HojaFuente({required this.procedencia});

  final List<Procedencia> procedencia;

  @override
  State<_HojaFuente> createState() => _HojaFuenteState();
}

class _HojaFuenteState extends State<_HojaFuente> {
  /// El fragmento resuelto de cada cita, por `chunk_id`.
  ///
  /// Si una llamada falla, su entrada simplemente no aparece: la ficha cae al
  /// respaldo de `Procedencia` —lo que ya se veía antes de esto— en vez de
  /// dejar la hoja entera sin abrir. Un fragmento que no se pudo traer no es
  /// una fuente inventada ni un error que haya que anunciar: es exactamente el
  /// mismo caso que "esto no tiene respaldo", que el diseño ya sabe mostrar.
  final Map<String, Fragmento> _fragmentos = <String, Fragmento>{};
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _cargar());
  }

  Future<void> _cargar() async {
    final Repositorios repos = context.read<Repositorios>();
    final List<String> ids = widget.procedencia
        .where((Procedencia c) => c.esDelMaterial)
        .map((Procedencia c) => c.fragmentoId)
        .whereType<String>()
        .toSet()
        .toList(growable: false);

    if (ids.isEmpty) {
      if (mounted) setState(() => _cargando = false);
      return;
    }

    await Future.wait(ids.map((String id) async {
      try {
        final Fragmento fragmento = await repos.documentos.fragmento(id);
        if (mounted) setState(() => _fragmentos[id] = fragmento);
      } catch (_) {
        // Esta cita se queda con el respaldo de `Procedencia`. Una fuente no
        // se inventa: si no se puede traer, no se muestra como si se hubiera
        // traído.
      }
    }));

    if (mounted) setState(() => _cargando = false);
  }

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final List<Procedencia> delMaterial = widget.procedencia
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
                  itemBuilder: (BuildContext contexto, int indice) {
                    final Procedencia cita = delMaterial[indice];
                    final Fragmento? fragmento = cita.fragmentoId == null
                        ? null
                        : _fragmentos[cita.fragmentoId];
                    final bool pendiente = _cargando && fragmento == null;
                    return _FichaCita(
                      cita: cita,
                      fragmento: fragmento,
                      cargando: pendiente,
                    );
                  },
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
  const _FichaCita({required this.cita, this.fragmento, this.cargando = false});

  final Procedencia cita;

  /// El fragmento traído de `GET /chunks/{id}`, si la llamada llegó a tiempo.
  final Fragmento? fragmento;

  /// Está en camino y aún no hay ni fragmento ni fallo.
  final bool cargando;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    // El fragmento manda cuando llega: es la única fuente real de título,
    // páginas y texto citado. `Procedencia` no los lleva —ver el porqué en
    // `_HojaFuenteState`— así que sin fragmento la ficha cae al mismo
    // respaldo que tenía antes de conectar esta llamada.
    final String? titulo = fragmento?.tituloDocumento ?? cita.tituloDocumento;
    final String paginas = fragmento?.referenciaPaginas ?? cita.referenciaPaginas;
    final String? extracto = fragmento?.texto ?? cita.extracto;

    if (cargando) {
      return TarjetaAtenea(
        hijo: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Esqueleto(alto: 20, ancho: 160),
            const SizedBox(height: Espacio.sm),
            const Esqueleto(alto: 14),
            const SizedBox(height: Espacio.xxs),
            const Esqueleto(alto: 14, ancho: 220),
          ],
        ),
      );
    }

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
                  titulo ?? 'Tu material',
                  style: context.textos.titleMedium,
                ),
              ),
            ],
          ),
          if (fragmento != null && fragmento!.encabezados.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.xxs),
            Text(
              fragmento!.encabezados.join(' › '),
              style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
            ),
          ],
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
