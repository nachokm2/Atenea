/// P05 · Crear ruta.
///
/// Captura objetivo, nivel y material en menos de dos minutos y deja claro que
/// el Reino hará el resto. Tres pasos en una sola pantalla con indicador, para
/// que nadie se pierda entre formularios.
///
/// Estados cubiertos: archivo rechazado con explicación, subida con progreso y
/// reintento, creación sin material (se avisa que el contenido será saber del
/// Reino), fallo de creación y límite del plan alcanzado.
library;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/aventura.dart';
import '../../estado/sesion.dart';
import '../../navegacion/rutas.dart';
import 'widgets/comunes_aventura.dart';
import 'widgets/hojas_aventura.dart';

/// Objetivos de ejemplo: se tocan y rellenan el campo.
const List<String> _sugerencias = <String>[
  'Aprender SQL para analizar datos',
  'Python desde cero para automatizar tareas',
  'Entender estadística para mi tesis',
  'Inglés para reuniones de trabajo',
  'Fundamentos de finanzas personales',
  'Preparar mi certificación de nube',
];

/// Minutos al día que se ofrecen (informativo, ayuda a dimensionar la ruta).
const List<int> _minutosSugeridos = <int>[5, 10, 20];

/// Pantalla de creación de una Ruta.
class PantallaCrearRuta extends StatefulWidget {
  const PantallaCrearRuta({super.key});

  @override
  State<PantallaCrearRuta> createState() => _PantallaCrearRutaState();
}

class _PantallaCrearRutaState extends State<PantallaCrearRuta> {
  late final TextEditingController _objetivo;

  @override
  void initState() {
    super.initState();
    _objetivo = TextEditingController(
      text: context.read<ControladorAventura>().objetivo,
    );
  }

  @override
  void dispose() {
    _objetivo.dispose();
    super.dispose();
  }

  // ---------------------------------------------------------------------
  // Acciones
  // ---------------------------------------------------------------------

  void _avisar(String mensaje) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(mensaje)));
  }

  void _usarSugerencia(String texto) {
    _objetivo.value = TextEditingValue(
      text: texto,
      selection: TextSelection.collapsed(offset: texto.length),
    );
    context.read<ControladorAventura>().fijarObjetivo(texto);
  }

  Future<void> _elegirArchivos() async {
    final ControladorAventura aventura = context.read<ControladorAventura>();
    List<PlatformFile> elegidos;
    try {
      elegidos = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: ControladorAventura.extensionesPermitidas,
      );
    } on Exception {
      _avisar('No pudimos abrir tus archivos. Inténtalo otra vez.');
      return;
    }
    if (!mounted || elegidos.isEmpty) return;

    for (final PlatformFile archivo in elegidos) {
      final List<int> datos;
      try {
        datos = await archivo.readAsBytes();
      } on Exception {
        if (!mounted) return;
        _avisar('No pudimos leer "${archivo.name}". Prueba con otro archivo.');
        continue;
      }
      if (!mounted) return;
      await aventura.agregarArchivo(
        nombreArchivo: archivo.name,
        bytes: datos,
      );
      if (!mounted) return;
    }
  }

  Future<void> _pegarTexto() async {
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final TextoPegado? pegado = await pedirTextoPegado(context);
    if (!mounted || pegado == null) return;
    final bool bien = await aventura.pegarTexto(
      titulo: pegado.titulo,
      texto: pegado.texto,
    );
    if (!bien) _avisar('No pudimos guardar ese texto. Inténtalo otra vez.');
  }

  Future<void> _crear() async {
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final String? rutaId = await aventura.crearRuta();
    if (!mounted || rutaId == null) return;
    sesion.anotarRuta();
    aventura.reiniciarBorrador();
    _objetivo.clear();
    context.pushReplacement(Rutas.generacion(rutaId));
  }

  void _cerrar() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Rutas.aventura);
    }
  }

  // ---------------------------------------------------------------------
  // Construcción
  // ---------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorAventura aventura = context.watch<ControladorAventura>();
    final AteneaPalette p = context.paleta;

    return PantallaAtenea(
      titulo: 'Nueva ruta',
      cerrarEnLugarDeVolver: true,
      alCerrar: _cerrar,
      padding: const EdgeInsets.fromLTRB(
        Espacio.md,
        0,
        Espacio.md,
        Espacio.lg,
      ),
      encabezado: _Pasos(
        objetivoListo: aventura.objetivoValido,
        materialListo: !aventura.subiendoArchivos,
      ),
      piePersistente: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (!aventura.puedeCrear && !aventura.creando)
            Padding(
              padding: const EdgeInsets.only(bottom: Espacio.xs),
              child: Text(
                aventura.subiendoArchivos
                    ? 'Esperamos a que termine de subir tu material…'
                    : 'Cuéntanos primero qué quieres aprender.',
                style:
                    context.textos.bodySmall?.copyWith(color: p.textoSecundario),
                textAlign: TextAlign.center,
              ),
            ),
          BotonPrimario(
            texto: 'Construir mi ruta',
            subtitulo: aventura.modoFuente == ModoFuente.conFuente
                ? 'Con tu material'
                : 'Con el saber del Reino',
            icono: Icons.auto_awesome_rounded,
            cargando: aventura.creando,
            alTocar: aventura.puedeCrear ? _crear : null,
          ),
        ],
      ),
      cuerpo: ListView(
        children: <Widget>[
          const SizedBox(height: Espacio.xs),
          ..._pasoObjetivo(aventura),
          ..._pasoNivel(aventura),
          ..._pasoMaterial(aventura),
          if (aventura.errorCreacion != null) ...<Widget>[
            const SizedBox(height: Espacio.md),
            _avisoDeCreacion(aventura.errorCreacion!),
          ],
          const SizedBox(height: Espacio.md),
          Text(
            'Tu borrador se guarda: puedes salir y volver sin perder nada.',
            style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  // --- Paso 1 -----------------------------------------------------------

  List<Widget> _pasoObjetivo(ControladorAventura aventura) {
    final AteneaPalette p = context.paleta;
    return <Widget>[
      const EncabezadoSeccion(
        titulo: '¿Qué quieres aprender?',
        subtitulo: 'Escríbelo con tus palabras. Cuanto más concreto, mejor '
            'será el camino.',
      ),
      TextField(
        controller: _objetivo,
        minLines: 2,
        maxLines: 4,
        maxLength: 240,
        textCapitalization: TextCapitalization.sentences,
        onChanged: aventura.fijarObjetivo,
        decoration: const InputDecoration(
          hintText: 'Quiero aprender SQL para analizar datos en mi trabajo',
          counterText: '',
        ),
      ),
      const SizedBox(height: Espacio.sm),
      Text(
        'Ideas para empezar',
        style: context.textos.labelSmall?.copyWith(color: p.textoSecundario),
      ),
      const SizedBox(height: Espacio.xs),
      Wrap(
        spacing: Espacio.xs,
        runSpacing: Espacio.xs,
        children: <Widget>[
          for (final String idea in _sugerencias)
            ActionChip(
              avatar: Icon(Icons.bolt_rounded, size: 16, color: p.arcano),
              label: Text(idea),
              onPressed: () => _usarSugerencia(idea),
            ),
        ],
      ),
    ];
  }

  // --- Paso 2 -----------------------------------------------------------

  List<Widget> _pasoNivel(ControladorAventura aventura) {
    final AteneaPalette p = context.paleta;
    return <Widget>[
      const EncabezadoSeccion(
        titulo: 'Tu punto de partida',
        subtitulo: 'Nadie empieza tarde. Esto solo ajusta la dificultad.',
      ),
      Wrap(
        spacing: Espacio.xs,
        runSpacing: Espacio.xs,
        children: <Widget>[
          for (final NivelDeclarado nivel in NivelDeclarado.values)
            ChoiceChip(
              selected: aventura.nivel == nivel,
              label: Text(nivel.etiqueta),
              onSelected: (_) => aventura.fijarNivel(nivel),
            ),
        ],
      ),
      const SizedBox(height: Espacio.md),
      Text(
        'Tiempo que puedes dedicarle al día',
        style: context.textos.labelSmall?.copyWith(color: p.textoSecundario),
      ),
      const SizedBox(height: Espacio.xs),
      Wrap(
        spacing: Espacio.xs,
        runSpacing: Espacio.xs,
        children: <Widget>[
          for (final int minutos in _minutosSugeridos)
            ChoiceChip(
              selected: aventura.minutosAlDia == minutos,
              avatar: Icon(
                Icons.hourglass_bottom_rounded,
                size: 16,
                color: aventura.minutosAlDia == minutos
                    ? p.sobreArcano
                    : p.textoSecundario,
              ),
              label: Text('$minutos min'),
              onSelected: (_) => aventura.fijarMinutosAlDia(minutos),
            ),
        ],
      ),
    ];
  }

  // --- Paso 3 -----------------------------------------------------------

  List<Widget> _pasoMaterial(ControladorAventura aventura) {
    final AteneaPalette p = context.paleta;
    final List<SubidaDocumento> adjuntos = aventura.adjuntos;
    final int megas = (aventura.bytesAdjuntos / (1024 * 1024)).round();

    return <Widget>[
      const EncabezadoSeccion(
        titulo: 'Tu material',
        subtitulo: 'Opcional, pero cambia todo: con tus documentos cada '
            'lección cita de dónde viene lo que estudias.',
      ),
      Row(
        children: <Widget>[
          Expanded(
            child: SizedBox(
              height: Medida.areaTactilMin,
              child: OutlinedButton.icon(
                onPressed: _elegirArchivos,
                icon: const Icon(Icons.upload_file_rounded),
                label: const Text('Agregar archivos'),
              ),
            ),
          ),
          const SizedBox(width: Espacio.xs),
          SizedBox(
            height: Medida.areaTactilMin,
            child: OutlinedButton.icon(
              onPressed: _pegarTexto,
              icon: const Icon(Icons.content_paste_rounded),
              label: const Text('Pegar texto'),
            ),
          ),
        ],
      ),
      const SizedBox(height: Espacio.xs),
      Text(
        'PDF, DOCX, TXT y MD · hasta ${ControladorAventura.maxArchivos} '
        'archivos y 50 MB en total'
        '${adjuntos.isEmpty ? '' : ' · llevas $megas MB'}',
        style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
      ),
      if (aventura.avisoArchivo != null) ...<Widget>[
        const SizedBox(height: Espacio.sm),
        TarjetaAviso(
          icono: Icons.info_outline_rounded,
          color: p.advertencia,
          titulo: 'Ese archivo no entra',
          mensaje: aventura.avisoArchivo!,
        ),
      ],
      if (adjuntos.isEmpty) ...<Widget>[
        const SizedBox(height: Espacio.sm),
        TarjetaAviso(
          icono: Icons.auto_stories_rounded,
          color: p.info,
          titulo: 'Sin material: el Reino pone el suyo',
          mensaje: 'Construiremos la ruta con conocimiento general y lo '
              'marcaremos como "Saber del Reino" en cada lección. Puedes '
              'agregar documentos ahora o crear otra ruta con ellos más '
              'adelante.',
        ),
      ] else ...<Widget>[
        const SizedBox(height: Espacio.sm),
        for (final SubidaDocumento adjunto in adjuntos)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.xs),
            child: _FilaAdjunto(
              adjunto: adjunto,
              alQuitar: () => aventura.quitarArchivo(adjunto.id),
              alReintentar: () => aventura.reintentarSubida(adjunto.id),
            ),
          ),
      ],
    ];
  }

  Widget _avisoDeCreacion(ErrorAtenea error) {
    final AteneaPalette p = context.paleta;
    if (error.esCuotaAgotada) {
      return TarjetaAviso(
        icono: Icons.workspace_premium_outlined,
        color: p.advertencia,
        titulo: 'Has llegado al límite de rutas',
        mensaje: 'Tu plan no admite otra ruta nueva por ahora. Nada se detiene: '
            'puedes seguir avanzando en las rutas que ya tienes y en las Rutas '
            'del Reino, que son ilimitadas.',
        textoAccion: 'Ir a mis territorios',
        alTocarAccion: () => context.go(Rutas.aventura),
      );
    }
    return TarjetaAviso(
      icono: Icons.error_outline_rounded,
      color: p.error,
      titulo: 'No pudimos crear la ruta',
      mensaje: error.mensaje,
      textoAccion: error.esReintentable ? 'Intentar de nuevo' : null,
      alTocarAccion: error.esReintentable ? _crear : null,
    );
  }
}

// -------------------------------------------------------------------------
// Piezas
// -------------------------------------------------------------------------

/// Indicador de los tres pasos, siempre visible bajo la barra superior.
class _Pasos extends StatelessWidget {
  const _Pasos({required this.objetivoListo, required this.materialListo});

  final bool objetivoListo;
  final bool materialListo;

  @override
  Widget build(BuildContext context) {
    final List<(String, bool)> pasos = <(String, bool)>[
      ('Objetivo', objetivoListo),
      ('Nivel', objetivoListo),
      ('Material', objetivoListo && materialListo),
    ];
    return Row(
      children: <Widget>[
        for (int i = 0; i < pasos.length; i++) ...<Widget>[
          Expanded(
            child: _Paso(
              numero: i + 1,
              texto: pasos[i].$1,
              listo: pasos[i].$2,
            ),
          ),
          if (i < pasos.length - 1) const SizedBox(width: Espacio.xs),
        ],
      ],
    );
  }
}

class _Paso extends StatelessWidget {
  const _Paso({required this.numero, required this.texto, required this.listo});

  final int numero;
  final String texto;
  final bool listo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = listo ? p.arcano : p.textoSecundario;
    return Semantics(
      label: 'Paso $numero, $texto, ${listo ? 'listo' : 'pendiente'}',
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(
                  listo
                      ? Icons.check_circle_rounded
                      : Icons.radio_button_unchecked_rounded,
                  size: 15,
                  color: color,
                ),
                const SizedBox(width: Espacio.xxs),
                Flexible(
                  child: Text(
                    texto,
                    style: context.textos.bodySmall?.copyWith(
                      color: color,
                      fontWeight: FontWeight.w700,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: Espacio.xxs),
            AnimatedContainer(
              duration: Movimiento.corta,
              height: 3,
              decoration: BoxDecoration(
                color: listo ? p.arcano : p.borde,
                borderRadius: Redondeo.rPildora,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Un archivo adjunto con su estado, su progreso y sus salidas.
class _FilaAdjunto extends StatelessWidget {
  const _FilaAdjunto({
    required this.adjunto,
    required this.alQuitar,
    required this.alReintentar,
  });

  final SubidaDocumento adjunto;
  final VoidCallback alQuitar;
  final VoidCallback alReintentar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final (Color color, IconData icono, String estado) = switch (adjunto.estado) {
      EstadoSubida.pendiente => (
          p.textoSecundario,
          Icons.schedule_rounded,
          'En cola',
        ),
      EstadoSubida.subiendo => (p.info, Icons.upload_rounded, 'Subiendo'),
      EstadoSubida.listo => (
          p.exito,
          Icons.check_circle_rounded,
          'Listo para leer',
        ),
      EstadoSubida.fallida => (
          p.error,
          Icons.error_outline_rounded,
          'No se pudo subir',
        ),
    };

    return TarjetaAtenea(
      padding: const EdgeInsets.all(Espacio.sm),
      semantica: '${adjunto.nombreArchivo}, ${adjunto.tamanoLegible}, $estado',
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(icono, color: color, size: 20),
              const SizedBox(width: Espacio.xs),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      adjunto.nombreArchivo,
                      style: context.textos.bodyLarge,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      <String>[
                        if (adjunto.tamanoLegible.isNotEmpty)
                          adjunto.tamanoLegible,
                        estado,
                      ].join(' · '),
                      style: context.textos.bodySmall
                          ?.copyWith(color: p.textoSecundario),
                    ),
                  ],
                ),
              ),
              if (adjunto.estado == EstadoSubida.fallida)
                IconButton(
                  onPressed: alReintentar,
                  icon: const Icon(Icons.refresh_rounded),
                  tooltip: 'Reintentar la subida',
                ),
              IconButton(
                onPressed: alQuitar,
                icon: const Icon(Icons.close_rounded),
                tooltip: 'Quitar este archivo',
              ),
            ],
          ),
          if (adjunto.estado == EstadoSubida.subiendo) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            BarraProgreso(
              valor: adjunto.fraccion,
              color: p.info,
              alto: 6,
            ),
          ],
          if (adjunto.error != null) ...<Widget>[
            const SizedBox(height: Espacio.xxs),
            Text(
              adjunto.error!,
              style: context.textos.bodySmall?.copyWith(color: p.error),
            ),
          ],
        ],
      ),
    );
  }
}
