/// P11 — Desafío del módulo.
///
/// Dos momentos en una sola pantalla: la **entrada** con las reglas y la
/// recompensa anunciada por el servidor, y el **desafío** con las preguntas
/// del banco. Durante el desafío la retroalimentación es mínima (acierto o no,
/// sin explicación): la explicación se difiere a P12 para no convertir el
/// desafío en una lección.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/evaluacion.dart';
import '../../navegacion/rutas.dart';
import '../leccion/widgets/widgets_pregunta.dart';

/// Entrada y desarrollo del Desafío del módulo.
class PantallaEvaluacion extends StatefulWidget {
  const PantallaEvaluacion({required this.moduloId, super.key});

  /// Módulo que se evalúa.
  final String moduloId;

  @override
  State<PantallaEvaluacion> createState() => _PantallaEvaluacionState();
}

class _PantallaEvaluacionState extends State<PantallaEvaluacion> {
  final Map<String, Object?> _marcado = <String, Object?>{};

  bool _pedida = false;
  bool _navegando = false;
  String? _intentoId;
  bool? _destello;
  Timer? _relojDestello;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) => _abrir());
  }

  @override
  void dispose() {
    _relojDestello?.cancel();
    super.dispose();
  }

  Future<void> _abrir() async {
    if (_pedida || !mounted) return;
    _pedida = true;
    final ControladorEvaluacion control = context.read<ControladorEvaluacion>();
    if (control.info?.moduloId == widget.moduloId && control.info != null) {
      return;
    }
    await control.abrir(widget.moduloId);
  }

  Future<void> _reintentarCarga() async {
    _pedida = false;
    context.read<ControladorEvaluacion>().limpiarError();
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

  @override
  Widget build(BuildContext context) {
    final ControladorEvaluacion control = context.watch<ControladorEvaluacion>();

    // Un intento nuevo empieza con la pizarra limpia.
    final String? intentoId = control.intento?.id;
    if (intentoId != _intentoId) {
      _intentoId = intentoId;
      _marcado.clear();
    }
    if (control.fase != FaseEvaluacion.resultado) _navegando = false;

    if (control.fase == FaseEvaluacion.resultado) {
      _irAlResultado();
      return const PantallaAtenea(
        cuerpo: EstadoCarga(mensaje: 'Revisando tus respuestas…'),
      );
    }
    if (control.fase == FaseEvaluacion.enviando) {
      return const PantallaAtenea(
        cuerpo: EstadoCarga(mensaje: 'Calculando tu puntaje…'),
      );
    }

    _avisarError(control);

    if (control.cargando && control.info == null) return const _Esqueleto();
    if (control.error != null && control.info == null) {
      return PantallaAtenea(
        cerrarEnLugarDeVolver: true,
        alCerrar: _salir,
        cuerpo: EstadoError(
          titulo: 'No pudimos abrir el desafío',
          mensaje: control.error!.mensaje,
          alReintentar: _reintentarCarga,
        ),
      );
    }
    if (control.info == null) {
      return PantallaAtenea(
        cerrarEnLugarDeVolver: true,
        alCerrar: _salir,
        cuerpo: EstadoVacio(
          icono: Icons.shield_outlined,
          titulo: 'Este módulo aún no tiene desafío',
          mensaje:
              'Completa sus lecciones y el Reino preparará las preguntas.',
          textoAccion: 'Volver',
          alTocarAccion: _salir,
        ),
      );
    }

    return control.fase == FaseEvaluacion.enCurso
        ? _desafio(control)
        : _entrada(control);
  }

  // -------------------------------------------------------------------------
  // Entrada
  // -------------------------------------------------------------------------

  Widget _entrada(ControladorEvaluacion control) {
    final InfoEvaluacion info = control.info!;
    final AteneaPalette p = context.paleta;
    final ResumenEvaluacion ev = info.evaluacion;
    final RecompensaSimple? premio = info.vistaPreviaRecompensa;
    final bool reintento = info.intentosUsados > 0;

    return PantallaAtenea(
      cerrarEnLugarDeVolver: true,
      alCerrar: _salir,
      piePersistente: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          BotonPrimario(
            texto: reintento ? 'Intentarlo de nuevo' : 'Comenzar',
            icono: Icons.play_arrow_rounded,
            cargando: control.cargando,
            alTocar: info.puedeEmpezar ? () => control.comenzar() : null,
          ),
          if (!info.puedeEmpezar)
            Padding(
              padding: const EdgeInsets.only(top: Espacio.xs),
              child: Text(
                info.motivoBloqueo ??
                    (info.enEnfriamiento
                        ? 'Vuelve cuando termine el descanso.'
                        : 'Termina las lecciones del módulo para abrir el desafío.'),
                textAlign: TextAlign.center,
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ),
        ],
      ),
      cuerpo: ListView(
        children: <Widget>[
          _Escudo(titulo: info.tituloModulo ?? ev.titulo),
          const SizedBox(height: Espacio.lg),
          TarjetaAtenea(
            hijo: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text('Las reglas', style: context.textos.titleMedium),
                const SizedBox(height: Espacio.xs),
                FilaDato(
                  icono: Icons.format_list_numbered_rounded,
                  etiqueta: 'Preguntas',
                  valor: '${ev.preguntas}',
                ),
                FilaDato(
                  icono: Icons.verified_outlined,
                  etiqueta: 'Para superarlo',
                  valor: '${ev.puntajeAprobacion.round()} %',
                ),
                const FilaDato(
                  icono: Icons.timer_off_outlined,
                  etiqueta: 'Tiempo',
                  valor: 'Sin límite',
                ),
                FilaDato(
                  icono: Icons.replay_rounded,
                  etiqueta: 'Intentos de hoy',
                  valor: '${info.intentosRestantes} de '
                      '${ev.intentosMaximosPorDia}',
                ),
                if (info.mejorPuntaje != null)
                  FilaDato(
                    icono: Icons.emoji_events_outlined,
                    etiqueta: 'Tu mejor marca',
                    valor: '${info.mejorPuntaje!.round()} %',
                  ),
                if (info.intentosDePorVida > 0)
                  FilaDato(
                    icono: Icons.history_rounded,
                    etiqueta: 'Intentos en total',
                    valor: '${info.intentosDePorVida}',
                  ),
                for (final String regla in info.reglas)
                  Padding(
                    padding: const EdgeInsets.only(top: Espacio.xs),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Icon(
                          Icons.chevron_right_rounded,
                          size: 18,
                          color: p.textoSecundario,
                        ),
                        Expanded(
                          child: Text(regla, style: context.textos.bodyMedium),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          if (premio != null && !premio.estaVacia) ...<Widget>[
            const SizedBox(height: Espacio.sm),
            TarjetaAtenea(
              colorBorde: p.oro,
              hijo: Row(
                children: <Widget>[
                  Icon(Icons.card_giftcard_rounded, color: p.oro),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'Si lo superas',
                          style: context.textos.labelSmall?.copyWith(
                            color: p.textoSecundario,
                          ),
                        ),
                        Text(
                          premio.resumen,
                          style: Cifras.media(context).copyWith(color: p.oro),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (info.temas.isNotEmpty) ...<Widget>[
            const EncabezadoSeccion(titulo: 'Qué entra'),
            Wrap(
              spacing: Espacio.xs,
              runSpacing: Espacio.xs,
              children: <Widget>[
                for (final String tema in info.temas)
                  Pildora(texto: tema, icono: Icons.bookmark_outline_rounded),
              ],
            ),
          ],
          if (info.enEnfriamiento) ...<Widget>[
            const SizedBox(height: Espacio.md),
            _Nota(
              icono: Icons.self_improvement_rounded,
              color: p.info,
              texto: 'Tómate un respiro: podrás volver a intentarlo '
                  '${_tiempoHasta(info.enfriamientoHasta!)}. Aprovecha para '
                  'repasar los temas que se te resistieron.',
            ),
          ] else if (reintento) ...<Widget>[
            const SizedBox(height: Espacio.md),
            _Nota(
              icono: Icons.shuffle_rounded,
              color: p.dominio,
              texto: 'Preguntas distintas esta vez. Nada de lo aprendido se '
                  'pierde por volver a intentarlo.',
            ),
          ],
          const SizedBox(height: Espacio.md),
        ],
      ),
    );
  }

  // -------------------------------------------------------------------------
  // Desafío
  // -------------------------------------------------------------------------

  Widget _desafio(ControladorEvaluacion control) {
    final Pregunta? pregunta = control.preguntaActual;
    final bool quieto = reducirMovimiento(context);

    return PantallaAtenea(
      titulo: 'Desafío del módulo',
      cerrarEnLugarDeVolver: true,
      alCerrar: _salir,
      acciones: <Widget>[
        Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: Espacio.md),
            child: Semantics(
              label: 'Pregunta ${control.indice + 1} de ${control.total}',
              child: ExcludeSemantics(
                child: Text(
                  '${control.indice + 1}/${control.total}',
                  style: Cifras.pequena(context),
                ),
              ),
            ),
          ),
        ),
      ],
      encabezado: _Puntos(total: control.total, actual: control.indice),
      piePersistente: BotonPrimario(
        texto: control.esUltima ? 'Enviar respuestas' : 'Comprobar',
        cargando: control.registrando,
        alTocar: control.puedeResponder ? _responder : null,
      ),
      cuerpo: ListView(
        padding: const EdgeInsets.only(bottom: Espacio.lg),
        children: <Widget>[
          if (_destello != null)
            Padding(
              padding: const EdgeInsets.only(bottom: Espacio.sm),
              child: _Destello(acierto: _destello!, quieto: quieto),
            ),
          if (pregunta != null)
            VistaPregunta(
              key: ValueKey<String>('desafio-${pregunta.id}'),
              pregunta: pregunta,
              valorInicial: _marcado[pregunta.id],
              bloqueado: control.registrando,
              alCambiar: (Object? valor) {
                _marcado[pregunta.id] = valor;
                control.seleccionar(valor);
              },
            ),
        ],
      ),
    );
  }

  Future<void> _responder() async {
    final ControladorEvaluacion control = context.read<ControladorEvaluacion>();
    final bool ultima = control.esUltima;
    await control.responder();
    if (!mounted) return;
    if (control.error != null) return;
    _mostrarDestello(control.ultimoAcierto);
    if (ultima) await control.enviar();
  }

  void _mostrarDestello(bool? acierto) {
    if (acierto == null) return;
    _relojDestello?.cancel();
    setState(() => _destello = acierto);
    _relojDestello = Timer(Movimiento.celebracion, () {
      if (!mounted) return;
      setState(() => _destello = null);
    });
  }

  void _irAlResultado() {
    if (_navegando) return;
    _navegando = true;
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      context.go(Rutas.resultadoEvaluacion(widget.moduloId));
    });
  }

  void _avisarError(ControladorEvaluacion control) {
    final String? mensaje = control.error?.mensaje;
    if (mensaje == null || control.info == null) return;
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      control.limpiarError();
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(mensaje)));
    });
  }

  static String _tiempoHasta(DateTime momento) {
    final Duration falta = momento.difference(DateTime.now());
    if (falta.inMinutes <= 1) return 'en un minuto';
    if (falta.inHours < 1) return 'en ${falta.inMinutes} minutos';
    if (falta.inHours < 24) {
      final int minutos = falta.inMinutes % 60;
      return minutos == 0
          ? 'en ${falta.inHours} h'
          : 'en ${falta.inHours} h $minutos min';
    }
    return 'mañana';
  }
}

// ---------------------------------------------------------------------------
// Piezas
// ---------------------------------------------------------------------------

/// Emblema de entrada del desafío.
class _Escudo extends StatelessWidget {
  const _Escudo({required this.titulo});

  final String titulo;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Column(
      children: <Widget>[
        Container(
          width: 96,
          height: 96,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: p.arcano.withValues(alpha: 0.14),
            border: Border.all(color: p.arcano, width: 2),
          ),
          child: Icon(Icons.shield_rounded, size: 48, color: p.arcano),
        ),
        const SizedBox(height: Espacio.md),
        Text(
          'DESAFÍO DEL MÓDULO',
          style: context.textos.labelSmall?.copyWith(color: p.textoSecundario),
        ),
        const SizedBox(height: Espacio.xxs),
        Text(
          titulo,
          textAlign: TextAlign.center,
          style: context.textos.displaySmall,
        ),
        const SizedBox(height: Espacio.xs),
        Text(
          'Sin prisa y sin trampas: mide lo que ya dominas.',
          textAlign: TextAlign.center,
          style: context.textos.bodyLarge?.copyWith(color: p.textoSecundario),
        ),
      ],
    );
  }
}

/// Progreso por puntos (1/10) del desafío.
class _Puntos extends StatelessWidget {
  const _Puntos({required this.total, required this.actual});

  final int total;
  final int actual;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    if (total <= 0) return const SizedBox.shrink();
    if (total > 14) {
      return BarraProgreso(valor: (actual + 1) / total, alto: 8);
    }
    return ExcludeSemantics(
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          for (int i = 0; i < total; i++)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 3),
              child: AnimatedContainer(
                duration: Movimiento.corta,
                curve: Movimiento.estandar,
                width: i == actual ? 14 : 10,
                height: 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i < actual
                      ? p.arcano
                      : (i == actual ? p.oro : p.borde),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Retroalimentación mínima del desafío: acierto o no, sin explicación.
class _Destello extends StatelessWidget {
  const _Destello({required this.acierto, required this.quieto});

  final bool acierto;
  final bool quieto;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = acierto ? p.exito : p.advertencia;
    final String texto = acierto ? 'Correcto' : 'Anotado. Seguimos.';

    final Widget chip = Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Espacio.md,
        vertical: Espacio.xs,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: Redondeo.rPildora,
        border: Border.all(color: color),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            acierto ? Icons.check_circle_rounded : Icons.adjust_rounded,
            size: 18,
            color: color,
          ),
          const SizedBox(width: Espacio.xs),
          Text(
            texto,
            style: context.textos.bodyMedium?.copyWith(
              color: color,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );

    return Center(
      child: Semantics(
        liveRegion: true,
        label: texto,
        child: quieto
            ? chip
            : AnimatedOpacity(
                opacity: 1,
                duration: Movimiento.micro,
                child: chip,
              ),
      ),
    );
  }
}

class _Nota extends StatelessWidget {
  const _Nota({
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

class _Esqueleto extends StatelessWidget {
  const _Esqueleto();

  @override
  Widget build(BuildContext context) {
    return PantallaAtenea(
      cerrarEnLugarDeVolver: true,
      cuerpo: ListView(
        children: const <Widget>[
          SizedBox(height: Espacio.lg),
          Center(child: Esqueleto(alto: 96, ancho: 96, radio: Redondeo.pildora)),
          SizedBox(height: Espacio.md),
          Center(child: Esqueleto(alto: 24, ancho: 200)),
          SizedBox(height: Espacio.lg),
          Esqueleto(alto: 190, radio: Redondeo.tarjeta),
          SizedBox(height: Espacio.sm),
          Esqueleto(alto: 80, radio: Redondeo.tarjeta),
        ],
      ),
      piePersistente: const Esqueleto(alto: 52, radio: Redondeo.boton),
    );
  }
}
