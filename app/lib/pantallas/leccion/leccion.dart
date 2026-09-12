/// P08 — Lección, y P09 — Pregunta con retroalimentación.
///
/// Flujo inmersivo: un paso por pantalla, barra segmentada arriba, contador
/// discreto de XP, X para salir (el avance queda guardado) y un único CTA
/// abajo. Cuando el paso es una pregunta, el panel de retroalimentación sube
/// desde abajo con el veredicto, la explicación y la fuente.
///
/// Esta misma pantalla sirve al modo **repaso** (`/repaso/{temaId}`): solo
/// preguntas, con el aviso de que la XP de lección no se vuelve a pagar.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/leccion.dart';
import '../../navegacion/armazon.dart';
import '../../navegacion/rutas.dart';
import 'fin_leccion.dart';
import 'widgets/hoja_fuente.dart';
import 'widgets/panel_retroalimentacion.dart';
import 'widgets/texto_rico.dart';
import 'widgets/widgets_pregunta.dart';

/// Lección paso a paso (P08) con su panel de retroalimentación (P09).
class PantallaLeccion extends StatefulWidget {
  const PantallaLeccion({super.key, this.leccionId, this.temaId});

  /// Lección a estudiar. Nulo en el modo repaso.
  final String? leccionId;

  /// Tema a repasar. Nulo en una lección normal.
  final String? temaId;

  /// ¿Esta pantalla está en modo repaso?
  bool get esRepaso => leccionId == null && temaId != null;

  @override
  State<PantallaLeccion> createState() => _PantallaLeccionState();
}

class _PantallaLeccionState extends State<PantallaLeccion> {
  /// Lo que el usuario lleva marcado en cada pregunta, para que volver atrás
  /// no borre su elección.
  final Map<String, Object?> _marcado = <String, Object?>{};

  bool _pedida = false;
  bool _navegando = false;
  bool _reexplicando = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) => _abrir());
  }

  Future<void> _abrir() async {
    if (_pedida || !mounted) return;
    _pedida = true;
    final ControladorLeccion control = context.read<ControladorLeccion>();
    final String? leccionId = widget.leccionId;
    final String? temaId = widget.temaId;

    if (leccionId != null) {
      final bool yaAbierta =
          control.leccion?.id == leccionId && control.actividad != null;
      if (yaAbierta) return;
      await control.abrir(leccionId);
      return;
    }
    if (temaId != null) {
      final bool yaAbierto =
          control.actividad?.temaId == temaId && control.recibo == null;
      if (yaAbierto) return;
      await control.abrirRepaso(temaId);
    }
  }

  Future<void> _reintentar() async {
    _pedida = false;
    context.read<ControladorLeccion>().limpiarError();
    await _abrir();
  }

  void _salir() {
    final GoRouter enrutador = GoRouter.of(context);
    if (enrutador.canPop()) {
      enrutador.pop();
    } else {
      context.go(Rutas.inicio);
    }
  }

  // -------------------------------------------------------------------------
  // Construcción
  // -------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorLeccion control = context.watch<ControladorLeccion>();

    // Cierre: el recibo ya está y toca celebrar (P10). Se comprueba que el
    // recibo sea el de *esta* lección, y no el que quedó de la anterior.
    final bool esMiRecibo = widget.esRepaso
        ? control.actividad?.temaId == widget.temaId
        : control.leccion?.id == widget.leccionId;
    if (control.recibo != null && esMiRecibo) {
      if (widget.esRepaso) return const PantallaFinLeccion();
      _irAlResumen(control);
      return const PantallaAtenea(
        cuerpo: EstadoCarga(mensaje: 'Contando tus recompensas…'),
      );
    }

    _avisarError(control);

    final bool vacio = control.totalPasos == 0;
    if (control.cargando && vacio) return const _EsqueletoLeccion();
    if (control.error != null && vacio) {
      return PantallaAtenea(
        cerrarEnLugarDeVolver: true,
        alCerrar: _salir,
        cuerpo: EstadoError(
          titulo: 'No pudimos abrir la lección',
          mensaje: control.error!.mensaje,
          alReintentar: control.error!.esReintentable ? _reintentar : null,
        ),
      );
    }
    if (vacio) {
      return PantallaAtenea(
        cerrarEnLugarDeVolver: true,
        alCerrar: _salir,
        cuerpo: EstadoVacio(
          icono: Icons.auto_stories_outlined,
          titulo: 'Esta lección aún se está forjando',
          mensaje:
              'El Reino todavía no terminó su contenido. Vuelve en un momento '
              'o sigue con otro paso de tu Ruta.',
          textoAccion: 'Volver',
          alTocarAccion: _salir,
        ),
      );
    }

    final PasoLeccion? paso = control.pasoActual;
    final bool quieto = reducirMovimiento(context);

    return PantallaAtenea(
      cerrarEnLugarDeVolver: true,
      alCerrar: _salir,
      acciones: <Widget>[
        _ContadorXp(xp: control.xpDeRespuestas),
        _MenuLeccion(
          paso: paso,
          reexplicando: _reexplicando,
          alReexplicar: _reexplicar,
          alReportar: () => _reportar(paso),
          alVerFuente: () => mostrarHojaFuente(context, _procedenciaDe(paso)),
        ),
      ],
      encabezado: _BarraPasos(
        total: control.totalPasos,
        actual: control.indice,
      ),
      piePersistente: _pie(control, paso),
      cuerpo: ListView(
        padding: const EdgeInsets.only(bottom: Espacio.lg),
        children: <Widget>[
          _Encabezado(control: control, esRepaso: widget.esRepaso),
          const SizedBox(height: Espacio.md),
          AnimatedSwitcher(
            duration: quieto ? Duration.zero : Movimiento.corta,
            switchInCurve: Movimiento.estandar,
            transitionBuilder: (Widget hijo, Animation<double> animacion) =>
                FadeTransition(
              opacity: animacion,
              child: SlideTransition(
                position: Tween<Offset>(
                  begin: const Offset(0.08, 0),
                  end: Offset.zero,
                ).animate(animacion),
                child: hijo,
              ),
            ),
            child: KeyedSubtree(
              key: ValueKey<int>(control.indice),
              child: _contenido(control, paso),
            ),
          ),
        ],
      ),
    );
  }

  Widget _contenido(ControladorLeccion control, PasoLeccion? paso) {
    if (paso == null) return const SizedBox.shrink();
    final Pregunta? pregunta = paso.pregunta;
    if (pregunta != null) {
      return VistaPregunta(
        key: ValueKey<String>('pregunta-${pregunta.id}'),
        pregunta: pregunta,
        valorInicial: _marcado[pregunta.id],
        bloqueado: control.fasePregunta != FasePregunta.respondiendo,
        resultado: control.fasePregunta == FasePregunta.retroalimentacion
            ? control.resultado
            : null,
        alCambiar: (Object? valor) {
          _marcado[pregunta.id] = valor;
          control.seleccionar(valor);
        },
      );
    }
    final BloqueLeccion? bloque = paso.bloque;
    if (bloque == null) return const SizedBox.shrink();
    return _VistaBloque(bloque: bloque);
  }

  Widget _pie(ControladorLeccion control, PasoLeccion? paso) {
    final bool esPregunta = paso?.esPregunta ?? false;

    if (esPregunta &&
        control.fasePregunta == FasePregunta.retroalimentacion &&
        control.resultado != null) {
      return PanelRetroalimentacion(
        resultado: control.resultado!,
        reexplicando: _reexplicando,
        alReexplicar: control.resultado!.esCorrecta ? null : _reexplicar,
        textoContinuar:
            control.esUltimoPaso ? 'Terminar la lección' : 'Continuar',
        alContinuar: () => control.continuar(),
      );
    }

    final bool comprobando =
        control.fasePregunta == FasePregunta.comprobando;
    final String texto = esPregunta
        ? 'Comprobar'
        : (control.esUltimoPaso ? 'Terminar la lección' : 'Continuar');
    final VoidCallback? accion = esPregunta
        ? (control.puedeComprobar ? () => control.comprobar() : null)
        : (control.puedeContinuar ? () => control.continuar() : null);

    return Row(
      children: <Widget>[
        if (control.indice > 0)
          Padding(
            padding: const EdgeInsets.only(right: Espacio.xs),
            child: IconButton.filledTonal(
              tooltip: 'Paso anterior',
              onPressed: control.retroceder,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
          ),
        Expanded(
          child: BotonPrimario(
            texto: comprobando ? 'Comprobando…' : texto,
            cargando: comprobando || control.cerrando,
            alTocar: accion,
          ),
        ),
      ],
    );
  }

  // -------------------------------------------------------------------------
  // Acciones auxiliares
  // -------------------------------------------------------------------------

  void _irAlResumen(ControladorLeccion control) {
    if (_navegando) return;
    final String? id = widget.leccionId ?? control.leccion?.id;
    if (id == null) return;
    _navegando = true;
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.go(Rutas.finLeccion(id));
    });
  }

  void _avisarError(ControladorLeccion control) {
    final String? mensaje = control.error?.mensaje;
    if (mensaje == null) return;
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      control.limpiarError();
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(mensaje)));
    });
  }

  static List<Procedencia> _procedenciaDe(PasoLeccion? paso) =>
      paso?.bloque?.procedencia ??
      paso?.pregunta?.procedencia ??
      const <Procedencia>[];

  Future<void> _reexplicar() async {
    if (_reexplicando) return;
    setState(() => _reexplicando = true);
    final Explicacion? explicacion =
        await context.read<ControladorLeccion>().reexplicar();
    if (!mounted) return;
    setState(() => _reexplicando = false);
    if (explicacion == null || explicacion.cuerpo.isEmpty) return;
    await mostrarHoja<void>(
      context,
      constructor: (BuildContext hoja) =>
          _HojaExplicacion(explicacion: explicacion),
    );
  }

  Future<void> _reportar(PasoLeccion? paso) async {
    final String? id = paso?.bloque?.id ?? paso?.pregunta?.id;
    if (id == null) return;
    final TipoContenido tipo = paso?.pregunta != null
        ? TipoContenido.pregunta
        : TipoContenido.bloque;
    final String? motivo = await mostrarHoja<String>(
      context,
      constructor: (BuildContext hoja) => const _HojaReporte(),
    );
    if (motivo == null || !mounted) return;
    final bool bien = await context.read<ControladorLeccion>().reportar(
          tipoContenido: tipo,
          contenidoId: id,
          motivo: motivo,
        );
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(
            bien
                ? 'Gracias. Un escriba lo revisará.'
                : 'No pudimos enviar el aviso. Inténtalo más tarde.',
          ),
        ),
      );
  }
}

// ---------------------------------------------------------------------------
// Piezas de la pantalla
// ---------------------------------------------------------------------------

/// Barra segmentada: un segmento por paso (§P08).
class _BarraPasos extends StatelessWidget {
  const _BarraPasos({required this.total, required this.actual});

  final int total;
  final int actual;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    if (total <= 0) return const SizedBox.shrink();

    final Widget barra = total > 14
        ? BarraProgreso(
            valor: (actual + 1) / total,
            alto: 8,
          )
        : Row(
            children: <Widget>[
              for (int i = 0; i < total; i++)
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(right: i == total - 1 ? 0 : 4),
                    child: AnimatedContainer(
                      duration: Movimiento.corta,
                      curve: Movimiento.estandar,
                      height: 8,
                      decoration: BoxDecoration(
                        color: i <= actual ? p.oro : p.borde,
                        borderRadius: Redondeo.rPildora,
                      ),
                    ),
                  ),
                ),
            ],
          );

    return Semantics(
      label: 'Paso ${actual + 1} de $total',
      child: ExcludeSemantics(child: barra),
    );
  }
}

/// Contador discreto de XP acumulado en la lección.
class _ContadorXp extends StatelessWidget {
  const _ContadorXp({required this.xp});

  final int xp;

  @override
  Widget build(BuildContext context) {
    if (xp <= 0) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Espacio.xs),
      child: Center(
        child: Semantics(
          label: '$xp puntos de experiencia en esta lección',
          child: ExcludeSemantics(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(Medallon.xp.icono, size: 18, color: context.paleta.oro),
                const SizedBox(width: Espacio.xxs),
                CifraAnimada(
                  valor: xp,
                  prefijo: '+',
                  sufijo: ' XP',
                  estilo: Cifras.pequena(context).copyWith(
                    color: context.paleta.oro,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Menú de la lección: fuente, otra explicación y reporte de contenido.
class _MenuLeccion extends StatelessWidget {
  const _MenuLeccion({
    required this.paso,
    required this.reexplicando,
    required this.alReexplicar,
    required this.alReportar,
    required this.alVerFuente,
  });

  final PasoLeccion? paso;
  final bool reexplicando;
  final VoidCallback alReexplicar;
  final VoidCallback alReportar;
  final VoidCallback alVerFuente;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      tooltip: 'Más opciones',
      icon: const Icon(Icons.more_vert_rounded),
      onSelected: (String opcion) {
        switch (opcion) {
          case 'fuente':
            alVerFuente();
          case 'explicar':
            if (!reexplicando) alReexplicar();
          case 'reportar':
            alReportar();
        }
      },
      itemBuilder: (BuildContext contexto) => const <PopupMenuEntry<String>>[
        PopupMenuItem<String>(
          value: 'fuente',
          child: ListTile(
            leading: Icon(Icons.menu_book_rounded),
            title: Text('Ver fuente'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
        PopupMenuItem<String>(
          value: 'explicar',
          child: ListTile(
            leading: Icon(Icons.lightbulb_outline_rounded),
            title: Text('Explícamelo de otro modo'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
        PopupMenuItem<String>(
          value: 'reportar',
          child: ListTile(
            leading: Icon(Icons.flag_outlined),
            title: Text('Esto parece incorrecto'),
            contentPadding: EdgeInsets.zero,
          ),
        ),
      ],
    );
  }
}

/// Título, miga de pan y aviso de repaso.
class _Encabezado extends StatelessWidget {
  const _Encabezado({required this.control, required this.esRepaso});

  final ControladorLeccion control;
  final bool esRepaso;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Leccion? leccion = control.leccion;
    final String titulo = leccion?.titulo ??
        control.actividad?.tituloTema ??
        (esRepaso ? 'Repaso' : 'Lección');
    final String miga = leccion?.migaDePan ?? '';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        if (miga.isNotEmpty)
          Text(
            miga,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
          ),
        const SizedBox(height: Espacio.xxs),
        Text(titulo, style: context.textos.headlineMedium),
        if (esRepaso || (leccion?.esRepaso ?? false)) ...<Widget>[
          const SizedBox(height: Espacio.sm),
          _Aviso(
            icono: Icons.refresh_rounded,
            color: p.dominio,
            texto: 'Repaso: la XP de lección no se vuelve a pagar, pero las '
                'preguntas nuevas sí suman.',
          ),
        ],
        if (leccion?.contenidoEscaso ?? false) ...<Widget>[
          const SizedBox(height: Espacio.sm),
          _Aviso(
            icono: Icons.inventory_2_outlined,
            color: p.advertencia,
            texto: 'Tu material cubre este tema en parte. Completamos con '
                'conocimiento general, siempre marcado.',
          ),
        ],
      ],
    );
  }
}

class _Aviso extends StatelessWidget {
  const _Aviso({
    required this.icono,
    required this.color,
    required this.texto,
  });

  final IconData icono;
  final Color color;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Espacio.sm),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: Redondeo.rChip,
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 18, color: color),
          const SizedBox(width: Espacio.xs),
          Expanded(child: Text(texto, style: context.textos.bodyMedium)),
        ],
      ),
    );
  }
}

/// Un bloque de contenido en la superficie de lectura.
class _VistaBloque extends StatelessWidget {
  const _VistaBloque({required this.bloque});

  final BloqueLeccion bloque;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool esCierre = bloque.tipo == TipoBloque.resumen;
    final String? diagrama = bloque.diagrama;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (bloque.tipo != TipoBloque.explicacion)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.xs),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Pildora(
                texto: bloque.tipo.etiqueta,
                icono: switch (bloque.tipo) {
                  TipoBloque.ejemplo => Icons.lightbulb_outline_rounded,
                  TipoBloque.codigo => Icons.code_rounded,
                  TipoBloque.diagrama => Icons.account_tree_outlined,
                  TipoBloque.resumen => Icons.bookmark_added_outlined,
                  _ => Icons.article_outlined,
                },
                color: esCierre ? p.oro : p.textoSecundario,
              ),
            ),
          ),
        Stack(
          children: <Widget>[
            Container(
              padding: const EdgeInsets.all(Espacio.md),
              decoration: BoxDecoration(
                color: p.lectura,
                borderRadius: Redondeo.rTarjeta,
                border: Border.all(color: esCierre ? p.oro : p.borde),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  if (bloque.tipo == TipoBloque.codigo)
                    TarjetaCodigo(
                      codigo: bloque.cuerpo,
                      lenguaje: bloque.lenguaje,
                    )
                  else
                    TextoRico(
                      texto: bloque.cuerpo,
                      lenguajePorDefecto: bloque.lenguaje,
                    ),
                  if (diagrama != null && diagrama.isNotEmpty)
                    TarjetaCodigo(
                      codigo: diagrama,
                      titulo: 'DIAGRAMA',
                      copiable: false,
                    ),
                  if (bloque.reportado)
                    Padding(
                      padding: const EdgeInsets.only(top: Espacio.xs),
                      child: Pildora(
                        texto: 'Reportado, en revisión',
                        icono: Icons.flag_rounded,
                        color: p.advertencia,
                      ),
                    ),
                ],
              ),
            ),
            if (esCierre)
              Positioned(
                top: Espacio.xs,
                right: Espacio.xs,
                child: OrnamentoEsquina(color: p.oro),
              ),
          ],
        ),
        const SizedBox(height: Espacio.sm),
        ChipFuente(procedencia: bloque.procedencia),
      ],
    );
  }
}

/// Esqueleto mientras la lección viaja desde el Reino.
class _EsqueletoLeccion extends StatelessWidget {
  const _EsqueletoLeccion();

  @override
  Widget build(BuildContext context) {
    return PantallaAtenea(
      cerrarEnLugarDeVolver: true,
      encabezado: const Esqueleto(alto: 8, radio: Redondeo.pildora),
      cuerpo: ListView(
        children: const <Widget>[
          Esqueleto(alto: 12, ancho: 160),
          SizedBox(height: Espacio.sm),
          Esqueleto(alto: 28, ancho: 240),
          SizedBox(height: Espacio.lg),
          Esqueleto(alto: 180, radio: Redondeo.tarjeta),
          SizedBox(height: Espacio.md),
          Esqueleto(alto: 44, radio: Redondeo.pildora, ancho: 220),
        ],
      ),
      piePersistente: const Esqueleto(alto: 52, radio: Redondeo.boton),
    );
  }
}

/// Hoja con la re-explicación alternativa del tema.
class _HojaExplicacion extends StatelessWidget {
  const _HojaExplicacion({required this.explicacion});

  final Explicacion explicacion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
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
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(Icons.lightbulb_rounded, color: p.oro),
                const SizedBox(width: Espacio.xs),
                Expanded(
                  child: Text(
                    'Otra forma de verlo',
                    style: context.textos.headlineSmall,
                  ),
                ),
              ],
            ),
            if (explicacion.enfoque.isNotEmpty) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              Align(
                alignment: Alignment.centerLeft,
                child: Pildora(texto: explicacion.enfoque, color: p.arcano),
              ),
            ],
            const SizedBox(height: Espacio.sm),
            Flexible(
              child: SingleChildScrollView(
                child: TextoRico(texto: explicacion.cuerpo),
              ),
            ),
            if (explicacion.citas.isNotEmpty) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              ChipFuente(procedencia: explicacion.citas),
            ],
            const SizedBox(height: Espacio.md),
            BotonPrimario(
              texto: 'Ahora sí, seguimos',
              alTocar: () => Navigator.of(context).maybePop(),
            ),
          ],
        ),
      ),
    );
  }
}

/// Hoja para reportar un bloque o una pregunta.
class _HojaReporte extends StatelessWidget {
  const _HojaReporte();

  static const List<(String, String, IconData)> _motivos =
      <(String, String, IconData)>[
    ('contenido_incorrecto', 'La información es incorrecta', Icons.error_outline_rounded),
    ('fuera_de_tema', 'No corresponde al tema', Icons.explore_off_outlined),
    ('incompleto', 'Está incompleto o confuso', Icons.help_outline_rounded),
    ('otro', 'Otro motivo', Icons.more_horiz_rounded),
  ];

  @override
  Widget build(BuildContext context) {
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
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text('Esto parece incorrecto', style: context.textos.headlineSmall),
            const SizedBox(height: Espacio.xxs),
            Text(
              'Gracias por cuidar el Reino. Nos ayuda a corregirlo para todos.',
              style: context.textos.bodyMedium?.copyWith(
                color: context.paleta.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.md),
            for (final (String clave, String texto, IconData icono) in _motivos)
              Padding(
                padding: const EdgeInsets.only(bottom: Espacio.xs),
                child: TarjetaAtenea(
                  alTocar: () => Navigator.of(context).pop(clave),
                  padding: const EdgeInsets.symmetric(
                    horizontal: Espacio.md,
                    vertical: Espacio.sm,
                  ),
                  hijo: Row(
                    children: <Widget>[
                      Icon(icono, size: 20, color: context.paleta.textoSecundario),
                      const SizedBox(width: Espacio.sm),
                      Expanded(
                        child: Text(texto, style: context.textos.bodyLarge),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
