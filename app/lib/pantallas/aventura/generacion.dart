/// P06 · Estado de generación.
///
/// La pantalla más importante para la retención: la forja puede tardar
/// minutos y aquí se convierte en algo tolerable y, si se puede, en una
/// primera aventura.
///
/// Principios del documento de experiencia:
/// - Nunca una barra vacía: siempre hay etapas con nombre y un dato real.
/// - Generación progresiva: en cuanto el Módulo 1 está listo aparece el botón
///   dorado para empezar sin esperar al resto.
/// - Se puede salir: el Reino sigue trabajando y avisa al terminar.
/// - Estados difíciles con salida: material insuficiente, fallo y espera larga.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/aventura.dart';
import '../../estado/sesion.dart';
import '../../navegacion/rutas.dart';
import 'widgets/comunes_aventura.dart';
import 'widgets/etapas_generacion.dart';
import 'widgets/hojas_aventura.dart';

/// Voz del Reino durante la espera, una frase por tramo de avance.
const List<String> _vocesDelReino = <String>[
  'El Reino abre tus documentos y empieza a leer.',
  'Separamos las ideas que de verdad importan.',
  'Dibujamos las zonas de tu territorio.',
  'Escribimos tu primera lección con cuidado.',
  'Últimos detalles del camino.',
];

/// Pantalla de la forja de una Ruta.
class PantallaGeneracion extends StatefulWidget {
  const PantallaGeneracion({required this.rutaId, super.key});

  /// Ruta que se está forjando.
  final String rutaId;

  @override
  State<PantallaGeneracion> createState() => _PantallaGeneracionState();
}

class _PantallaGeneracionState extends State<PantallaGeneracion> {
  ControladorAventura? _aventura;
  String? _adoptando;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final ControladorAventura aventura = context.read<ControladorAventura>();
      aventura
        ..iniciarSondeo(widget.rutaId)
        ..abrirRuta(widget.rutaId)
        ..cargarRutas();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _aventura = context.read<ControladorAventura>();
  }

  @override
  void dispose() {
    _aventura?.detenerSondeo();
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

  void _salir({bool conAviso = true}) {
    if (conAviso) {
      _avisar('Seguimos forjando tu ruta. Te avisamos cuando esté lista.');
    }
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Rutas.aventura);
    }
  }

  void _verMapa() => context.pushReplacement(Rutas.ruta(widget.rutaId));

  Future<void> _confirmar(PoliticaCobertura politica) async {
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final bool bien = await aventura.confirmarEsquema(
      widget.rutaId,
      politicaCobertura: politica,
    );
    if (!mounted) return;
    if (!bien) {
      _avisar(aventura.errorRuta?.mensaje ??
          'No pudimos guardar tu decisión. Inténtalo otra vez.');
      return;
    }
    aventura.iniciarSondeo(widget.rutaId);
  }

  Future<void> _elegirPolitica(PoliticaCobertura actual) async {
    final PoliticaCobertura? elegida =
        await elegirPoliticaCobertura(context, actual: actual);
    if (!mounted || elegida == null) return;
    await _confirmar(elegida);
  }

  Future<void> _descartar() async {
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final bool seguro = await confirmarAccion(
      context,
      titulo: '¿Detener la forja?',
      mensaje: 'Se descarta esta ruta y el trabajo en curso. Podrás crear otra '
          'cuando quieras.',
      textoConfirmar: 'Detener y descartar',
    );
    if (!mounted || !seguro) return;
    aventura.detenerSondeo();
    final bool bien = await aventura.eliminarRuta(widget.rutaId);
    if (!mounted) return;
    if (!bien) {
      _avisar('No pudimos detenerla. Inténtalo otra vez.');
      return;
    }
    context.go(Rutas.aventura);
  }

  Future<void> _adoptarDelReino(ResumenRuta ruta) async {
    setState(() => _adoptando = ruta.id);
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final DetalleRuta? adoptada = await aventura.adoptar(ruta.id);
    if (!mounted) return;
    setState(() => _adoptando = null);
    if (adoptada == null) {
      _avisar('No pudimos abrir esa ruta ahora. Inténtalo de nuevo.');
      return;
    }
    sesion.anotarRuta();
    if (!mounted) return;
    context.push(Rutas.ruta(adoptada.id));
  }

  // ---------------------------------------------------------------------
  // Construcción
  // ---------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorAventura aventura = context.watch<ControladorAventura>();
    final AteneaPalette p = context.paleta;
    final EstadoGeneracion? generacion =
        aventura.rutaEnGeneracion == widget.rutaId ? aventura.generacion : null;
    final DetalleRuta? detalle =
        aventura.ruta?.id == widget.rutaId ? aventura.ruta : null;

    final bool fallo = generacion?.fallo ?? false;
    final bool termino = generacion?.termino ?? false;
    final bool listo = aventura.primerModuloListo;
    // El aviso de cobertura es para cuando el material de verdad no alcanza,
    // no para cuando la forja se rompió. `requiereAtencion` es el estado de un
    // trabajo que agotó sus reintentos, y tratarlo como una decisión de
    // cobertura le echaba al aprendiz la culpa de un fallo del servidor.
    final bool pideDecision = detalle?.puedeConfirmar ?? false;

    return PantallaAtenea(
      titulo: 'Construyendo tu ruta',
      cerrarEnLugarDeVolver: true,
      alCerrar: _salir,
      acciones: <Widget>[
        IconButton(
          onPressed: _descartar,
          icon: const Icon(Icons.delete_outline_rounded),
          tooltip: 'Detener y descartar esta ruta',
        ),
      ],
      cuerpo: ListView(
        children: <Widget>[
          if (detalle != null && detalle.ruta.titulo.isNotEmpty) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            Center(
              child: Text(
                detalle.ruta.titulo,
                style: context.textos.displaySmall,
                textAlign: TextAlign.center,
              ),
            ),
          ],
          const SizedBox(height: Espacio.md),
          _Anillo(
            generacion: generacion,
            fallo: fallo,
            termino: termino,
          ),
          const SizedBox(height: Espacio.md),
          Center(
            child: Text(
              _voz(generacion, listo: listo, termino: termino, fallo: fallo),
              style: context.textos.bodyLarge?.copyWith(color: p.textoSecundario),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: Espacio.md),
          if (aventura.tardaDemasiado && !termino && !fallo) ...<Widget>[
            FranjaEstado(
              icono: Icons.schedule_rounded,
              color: p.advertencia,
              mensaje: 'Está tardando más de lo normal. Te avisamos cuando '
                  'esté lista: no necesitas esperar aquí.',
            ),
            const SizedBox(height: Espacio.sm),
          ],
          if (aventura.errorGeneracion != null && !fallo) ...<Widget>[
            FranjaEstado(
              icono: Icons.cloud_off_rounded,
              color: p.info,
              mensaje: 'Perdimos contacto con el Reino, pero la forja sigue.',
              textoAccion: 'Reintentar',
              alTocarAccion: aventura.reintentarGeneracion,
            ),
            const SizedBox(height: Espacio.sm),
          ],
          TarjetaAtenea(
            hijo: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                ListaEtapas(etapas: etapasVisibles(generacion)),
                if (_estimacion(generacion).isNotEmpty) ...<Widget>[
                  const SizedBox(height: Espacio.sm),
                  Divider(color: p.borde, height: Espacio.md),
                  Row(
                    children: <Widget>[
                      Icon(
                        Icons.hourglass_bottom_rounded,
                        size: 18,
                        color: p.textoSecundario,
                      ),
                      const SizedBox(width: Espacio.xs),
                      Text(
                        _estimacion(generacion),
                        style: context.textos.bodyMedium
                            ?.copyWith(color: p.textoSecundario),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          if (pideDecision && !fallo) ...<Widget>[
            const SizedBox(height: Espacio.md),
            _avisoCobertura(detalle),
          ],
          if (fallo) ...<Widget>[
            const SizedBox(height: Espacio.md),
            TarjetaAviso(
              icono: Icons.report_gmailerrorred_rounded,
              color: p.error,
              titulo: 'No pudimos terminar tu ruta',
              mensaje: generacion?.error ??
                  'Algo se atascó en la forja. No gastamos nada de tu plan: '
                      'puedes volver a intentarlo ahora mismo.',
              textoAccion: 'Reintentar la forja',
              alTocarAccion: aventura.reintentarGeneracion,
              textoSecundario: 'Empezar una Ruta del Reino',
              alTocarSecundario: () => context.go(Rutas.aventura),
            ),
          ],
          if (listo || termino) ...<Widget>[
            const SizedBox(height: Espacio.md),
            _LlamadaPrimerModulo(termino: termino, alTocar: _verMapa),
          ],
          const SizedBox(height: Espacio.lg),
          ..._mientrasTanto(aventura),
          const SizedBox(height: Espacio.lg),
          Text(
            'Puedes salir de aquí. El Reino sigue forjando y te avisa cuando '
            'tu ruta esté lista.',
            style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------
  // Piezas del cuerpo
  // ---------------------------------------------------------------------

  String _voz(
    EstadoGeneracion? generacion, {
    required bool listo,
    required bool termino,
    required bool fallo,
  }) {
    if (fallo) return 'La forja se detuvo, pero nada se ha perdido.';
    if (termino) return 'El camino está trazado. Tu territorio te espera.';
    if (listo) {
      return 'El Módulo 1 ya está listo: puedes empezar mientras terminamos '
          'el resto.';
    }
    final double avance = (generacion?.porcentaje ?? 0).clamp(0, 100).toDouble();
    final int tramo =
        (avance ~/ 20).clamp(0, _vocesDelReino.length - 1).toInt();
    return _vocesDelReino[tramo];
  }

  String _estimacion(EstadoGeneracion? generacion) {
    if (generacion == null) return 'Suele tardar entre 2 y 5 minutos.';
    if (generacion.termino || generacion.fallo) return '';
    final String falta = duracionDesdeSegundos(generacion.segundosEstimados);
    if (falta.isEmpty) return 'Suele tardar entre 2 y 5 minutos.';
    return 'Tiempo estimado: $falta.';
  }

  Widget _avisoCobertura(DetalleRuta? detalle) {
    final AteneaPalette p = context.paleta;
    final List<AvisoCobertura> avisos =
        detalle?.avisosCobertura ?? const <AvisoCobertura>[];
    final PoliticaCobertura actual =
        detalle?.ruta.politicaCobertura ?? PoliticaCobertura.conocimientoDelModelo;

    return TarjetaAviso(
      icono: Icons.balance_rounded,
      color: p.advertencia,
      titulo: 'Tu material no cubre todo el objetivo',
      mensaje: avisos.isEmpty
          ? 'Algunos temas de tu objetivo no aparecen en los documentos que '
              'subiste. Nunca inventamos una fuente: dinos qué prefieres.'
          : avisos.first.mensaje,
      pie: avisos.length <= 1
          ? null
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                for (final AvisoCobertura aviso in avisos.take(4))
                  Padding(
                    padding: const EdgeInsets.only(bottom: Espacio.xxs),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Icon(
                          Icons.circle,
                          size: 6,
                          color: p.textoSecundario,
                        ),
                        const SizedBox(width: Espacio.xs),
                        Expanded(
                          child: Text(
                            aviso.tituloTema ?? aviso.mensaje,
                            style: context.textos.bodyMedium
                                ?.copyWith(color: p.textoSecundario),
                          ),
                        ),
                        Pildora(
                          texto: aviso.nivel.etiqueta,
                          color: p.advertencia,
                        ),
                      ],
                    ),
                  ),
              ],
            ),
      textoAccion: 'Completar con el saber del Reino',
      alTocarAccion: () => _confirmar(PoliticaCobertura.conocimientoDelModelo),
      textoSecundario: 'Ver otras opciones',
      alTocarSecundario: () => _elegirPolitica(actual),
    );
  }

  List<Widget> _mientrasTanto(ControladorAventura aventura) {
    final AteneaPalette p = context.paleta;
    final List<ResumenRuta> reino = aventura.delReino;
    final ResumenRuta? sugerida = reino.isEmpty ? null : reino.first;

    return <Widget>[
      const EncabezadoSeccion(
        titulo: 'Mientras tanto',
        subtitulo: 'Tu primera aventura no tiene por qué esperar.',
      ),
      if (sugerida != null)
        TarjetaAtenea(
          elevada: true,
          colorBorde: p.oro.withValues(alpha: 0.45),
          alTocar: () => context.push(Rutas.ruta(sugerida.id)),
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  EmblemaTerritorio(
                    nombre: sugerida.nombreConocimiento ?? sugerida.titulo,
                    iconoKey: sugerida.iconoKey,
                    colorAcento: sugerida.colorAcento,
                    tamano: 46,
                  ),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'Ruta del Reino',
                          style: context.textos.labelSmall
                              ?.copyWith(color: p.textoSecundario),
                        ),
                        Text(
                          sugerida.titulo,
                          style: context.textos.titleMedium,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: Espacio.sm),
              BotonPrimario(
                texto: 'Empezar ahora',
                subtitulo: duracionLegible(sugerida.minutosEstimados).isEmpty
                    ? 'Un camino ya trazado'
                    : duracionLegible(sugerida.minutosEstimados),
                icono: Icons.play_arrow_rounded,
                cargando: _adoptando == sugerida.id,
                alTocar: () => _adoptarDelReino(sugerida),
              ),
            ],
          ),
        ),
      const SizedBox(height: Espacio.xs),
      _Atajo(
        icono: Icons.checkroom_rounded,
        texto: 'Personalizar tu personaje',
        alTocar: () => context.go(Rutas.personaje),
      ),
      _Atajo(
        icono: Icons.explore_rounded,
        texto: 'Explorar el Reino',
        alTocar: () => context.go(Rutas.aventura),
      ),
    ];
  }
}

// -------------------------------------------------------------------------
// Piezas
// -------------------------------------------------------------------------

/// Anillo de la forja: avance global con su cifra en el centro.
class _Anillo extends StatelessWidget {
  const _Anillo({
    required this.generacion,
    required this.fallo,
    required this.termino,
  });

  final EstadoGeneracion? generacion;
  final bool fallo;
  final bool termino;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final double avance =
        (generacion?.porcentaje ?? 0).clamp(0, 100).toDouble() / 100;
    final Color color = fallo ? p.error : (termino ? p.oro : p.arcano);
    final bool indeterminado =
        !fallo && !termino && avance <= 0 && !reducirMovimiento(context);

    return Center(
      child: SizedBox(
        height: 148,
        width: 148,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            SizedBox(
              height: 148,
              width: 148,
              child: TweenAnimationBuilder<double>(
                tween: Tween<double>(begin: 0, end: avance),
                duration: Movimiento.transicion,
                curve: Movimiento.estandar,
                builder: (BuildContext context, double t, _) =>
                    CircularProgressIndicator(
                  value: indeterminado ? null : t,
                  strokeWidth: 10,
                  strokeCap: StrokeCap.round,
                  backgroundColor: p.borde,
                  valueColor: AlwaysStoppedAnimation<Color>(color),
                ),
              ),
            ),
            Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(
                  fallo
                      ? Icons.report_gmailerrorred_rounded
                      : (termino
                          ? Icons.check_circle_rounded
                          : Icons.local_fire_department_rounded),
                  color: color,
                  size: 26,
                ),
                const SizedBox(height: Espacio.xxs),
                Text(
                  fallo
                      ? 'Detenida'
                      : porcentajeLegible(generacion?.porcentaje ?? 0),
                  style: Cifras.grande(context),
                ),
                Text(
                  fallo ? 'la forja' : 'de la forja',
                  style: context.textos.bodySmall
                      ?.copyWith(color: p.textoSecundario),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Llamada dorada: el Módulo 1 ya se puede empezar (generación progresiva).
class _LlamadaPrimerModulo extends StatelessWidget {
  const _LlamadaPrimerModulo({required this.termino, required this.alTocar});

  final bool termino;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      elevada: true,
      colorBorde: p.oro,
      brillo: 14,
      hijo: Stack(
        children: <Widget>[
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                termino ? 'Tu ruta está lista' : 'El Módulo 1 ya te espera',
                style: context.textos.displaySmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: Espacio.xs),
              Text(
                termino
                    ? 'El territorio completo está trazado. Entra y elige por '
                        'dónde empezar.'
                    : 'No hace falta esperar al resto del camino: la primera '
                        'zona ya está escrita.',
                style:
                    context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: Espacio.md),
              BotonPrimario(
                texto: termino ? 'Ver el mapa de la ruta' : 'Empezar el Módulo 1',
                icono: Icons.map_rounded,
                alTocar: alTocar,
              ),
            ],
          ),
          Positioned(left: 0, top: 0, child: OrnamentoEsquina(color: p.oro)),
        ],
      ),
    );
  }
}

/// Atajo de una línea de la sección "Mientras tanto".
class _Atajo extends StatelessWidget {
  const _Atajo({
    required this.icono,
    required this.texto,
    required this.alTocar,
  });

  final IconData icono;
  final String texto;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return ListTile(
      minTileHeight: Medida.areaTactilMin,
      contentPadding: const EdgeInsets.symmetric(horizontal: Espacio.xs),
      leading: Icon(icono, color: p.textoSecundario),
      title: Text(texto, style: context.textos.bodyLarge),
      trailing: Icon(Icons.chevron_right_rounded, color: p.textoSecundario),
      shape: const RoundedRectangleBorder(borderRadius: Redondeo.rBoton),
      onTap: alTocar,
    );
  }
}
