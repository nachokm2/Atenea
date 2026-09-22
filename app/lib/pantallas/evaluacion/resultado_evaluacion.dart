/// P12 — Resultado del Desafío del módulo.
///
/// Nunca castiga: si no se superó, el titular es "Aún no", el color es ámbar
/// y el camino de vuelta está señalizado (reforzar los temas débiles, o
/// reintentar con preguntas distintas). El progreso y el dominio se conservan
/// siempre.
library;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/theme.dart';
import '../../design/tokens.dart';
import '../../estado/celebraciones.dart';
import '../../estado/evaluacion.dart';
import '../../navegacion/armazon.dart';
import '../../navegacion/rutas.dart';
import '../leccion/widgets/desglose_recompensas.dart';
import '../leccion/widgets/hoja_fuente.dart';
import '../leccion/widgets/texto_rico.dart';
import '../repaso/widgets/tarjeta_repaso.dart';

/// Puntaje, desglose por tema y siguiente paso tras el desafío.
class PantallaResultadoEvaluacion extends StatefulWidget {
  const PantallaResultadoEvaluacion({required this.moduloId, super.key});

  /// Módulo evaluado.
  final String moduloId;

  @override
  State<PantallaResultadoEvaluacion> createState() =>
      _PantallaResultadoEvaluacionState();
}

class _PantallaResultadoEvaluacionState
    extends State<PantallaResultadoEvaluacion> {
  bool _encolado = false;
  bool _cargandoRevision = false;
  bool _reintentando = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((Duration _) => _encolar());
  }

  void _encolar() {
    if (_encolado || !mounted) return;
    final ReciboRecompensas? recibo =
        context.read<ControladorEvaluacion>().recibo;
    if (recibo == null) return;
    _encolado = true;
    context.read<ColaCelebraciones>().encolar(recibo);
  }

  void _irA(String destino) {
    context.read<ColaCelebraciones>().vaciar();
    context.go(destino);
  }

  @override
  Widget build(BuildContext context) {
    final ControladorEvaluacion control = context.watch<ControladorEvaluacion>();
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final ResultadoEvaluacionModulo? resultado = control.resultado;
    final ReciboRecompensas? recibo = control.recibo;

    if (resultado == null) {
      return PantallaAtenea(
        cuerpo: EstadoVacio(
          icono: Icons.shield_outlined,
          titulo: 'Todavía no hay resultado',
          mensaje:
              'Cuando termines un Desafío del módulo, aquí encontrarás tu '
              'puntaje y qué conviene reforzar.',
          textoAccion: 'Volver al Inicio',
          alTocarAccion: () => _irA(Rutas.inicio),
        ),
      );
    }

    final AteneaPalette p = context.paleta;
    final bool aprobo = resultado.aprobo;
    final Color acento = aprobo ? p.exito : p.advertencia;
    final List<PuntajeTema> debiles = resultado.temasDebiles.isNotEmpty
        ? resultado.temasDebiles
        : resultado.porTema
            .where((PuntajeTema t) => t.esDebil)
            .toList(growable: false);
    final String? rutaId = control.info?.rutaId;

    return PantallaAtenea(
      piePersistente: _pie(
        control: control,
        aprobo: aprobo,
        debiles: debiles,
        rutaId: rutaId,
        resultado: resultado,
      ),
      cuerpo: ListView(
        children: <Widget>[
          _Marcador(resultado: resultado, acento: acento),
          if (resultado.puntajeEfectivo != null &&
              resultado.numeroIntento > 1) ...<Widget>[
            const SizedBox(height: Espacio.xs),
            Center(
              child: Pildora(
                texto: 'Intento ${resultado.numeroIntento} · dominio con '
                    '${resultado.puntajeEfectivo!.round()} %',
                icono: Icons.replay_rounded,
              ),
            ),
          ],
          const SizedBox(height: Espacio.lg),
          if (recibo != null) ...<Widget>[
            DesgloseRecompensas(
              recibo: recibo,
              etiquetaActividad: 'Desafío del módulo',
              respuestas: resultado.total,
            ),
            const SizedBox(height: Espacio.sm),
            BarraNivel(nivel: recibo.nivel, xpTotal: recibo.xp?.totalDespues),
            if (cola.chips.isNotEmpty) ...<Widget>[
              const SizedBox(height: Espacio.md),
              ChipsCelebracion(chips: cola.chips),
            ],
            if (recibo.desbloqueos.isNotEmpty) ...<Widget>[
              const SizedBox(height: Espacio.sm),
              ListaDesbloqueos(desbloqueos: recibo.desbloqueos),
            ],
            if (recibo.sincronizacionPendiente) ...<Widget>[
              const SizedBox(height: Espacio.sm),
              const AvisoSincronizacion(),
            ],
          ],
          if (resultado.porTema.isNotEmpty) ...<Widget>[
            const EncabezadoSeccion(
              titulo: 'Tema a tema',
              subtitulo: 'Dónde estuviste firme y dónde conviene volver',
            ),
            for (final PuntajeTema tema in resultado.porTema)
              _FilaTema(tema: tema),
          ],
          if (resultado.sugerenciasRepaso.isNotEmpty) ...<Widget>[
            const EncabezadoSeccion(titulo: 'Repasos recomendados'),
            for (final SugerenciaRepaso s in resultado.sugerenciasRepaso)
              TarjetaRepaso(
                sugerencia: s,
                alTocar: () => _irA(Rutas.repaso(s.temaId)),
              ),
          ],
          if (!aprobo) ...<Widget>[
            const SizedBox(height: Espacio.md),
            _NotaSinCastigo(
              enfriamiento: resultado.enfriamientoHasta,
              umbral: resultado.puntajeAprobacion,
            ),
          ],
          const SizedBox(height: Espacio.md),
        ],
      ),
    );
  }

  Widget _pie({
    required ControladorEvaluacion control,
    required bool aprobo,
    required List<PuntajeTema> debiles,
    required String? rutaId,
    required ResultadoEvaluacionModulo resultado,
  }) {
    final String? temaDeRefuerzo = debiles.isNotEmpty
        ? debiles.first.temaId
        : (resultado.sugerenciasRepaso.isNotEmpty
            ? resultado.sugerenciasRepaso.first.temaId
            : null);
    final bool puedeReintentar = !(control.info?.enEnfriamiento ?? false) &&
        (control.info?.intentosRestantes ?? 1) > 0;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (aprobo)
          BotonPrimario(
            texto: 'Continuar',
            icono: Icons.arrow_forward_rounded,
            subtitulo: rutaId == null ? null : 'Sigue tu Ruta',
            alTocar: () =>
                _irA(rutaId == null ? Rutas.inicio : Rutas.ruta(rutaId)),
          )
        else
          BotonPrimario(
            texto: 'Reforzar temas débiles',
            icono: Icons.auto_fix_high_rounded,
            alTocar: temaDeRefuerzo == null
                ? null
                : () => _irA(Rutas.repaso(temaDeRefuerzo)),
          ),
        Row(
          children: <Widget>[
            if (!aprobo)
              Expanded(
                child: TextButton(
                  onPressed: puedeReintentar && !_reintentando
                      ? _reintentar
                      : null,
                  child: Text(
                    _reintentando ? 'Preparando…' : 'Reintentar ahora',
                  ),
                ),
              ),
            Expanded(
              child: TextButton(
                onPressed: _cargandoRevision ? null : _revisar,
                child: Text(
                  _cargandoRevision ? 'Abriendo…' : 'Revisar respuestas',
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _reintentar() async {
    setState(() => _reintentando = true);
    final ControladorEvaluacion control = context.read<ControladorEvaluacion>();
    final bool listo = await control.reintentar();
    if (!mounted) return;
    setState(() => _reintentando = false);
    if (listo) {
      context.read<ColaCelebraciones>().vaciar();
      context.go(Rutas.evaluacion(widget.moduloId));
    }
  }

  Future<void> _revisar() async {
    setState(() => _cargandoRevision = true);
    final ControladorEvaluacion control = context.read<ControladorEvaluacion>();
    if (control.revision == null) await control.cargarRevision();
    if (!mounted) return;
    setState(() => _cargandoRevision = false);
    final RevisionEvaluacion? revision = control.revision;
    if (revision == null || revision.respuestas.isEmpty) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
          const SnackBar(
            content: Text(
              'La revisión todavía no está disponible. Inténtalo en un momento.',
            ),
          ),
        );
      return;
    }
    await mostrarHoja<void>(
      context,
      constructor: (BuildContext hoja) => _HojaRevision(revision: revision),
    );
  }
}

// ---------------------------------------------------------------------------
// Piezas
// ---------------------------------------------------------------------------

/// Anillo de puntaje con el titular del resultado.
class _Marcador extends StatelessWidget {
  const _Marcador({required this.resultado, required this.acento});

  final ResultadoEvaluacionModulo resultado;
  final Color acento;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool quieto = reducirMovimiento(context);
    final bool aprobo = resultado.aprobo;
    final int puntaje = resultado.puntaje.round();

    final Widget anillo = SizedBox(
      width: 148,
      height: 148,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          SizedBox.expand(
            child: quieto
                ? CircularProgressIndicator(
                    value: resultado.fraccion,
                    strokeWidth: 10,
                    backgroundColor: p.borde,
                    valueColor: AlwaysStoppedAnimation<Color>(acento),
                  )
                : TweenAnimationBuilder<double>(
                    tween: Tween<double>(begin: 0, end: resultado.fraccion),
                    duration: Movimiento.celebracion,
                    curve: Movimiento.estandar,
                    builder: (BuildContext contexto, double v, Widget? hijo) =>
                        CircularProgressIndicator(
                      value: v,
                      strokeWidth: 10,
                      backgroundColor: p.borde,
                      valueColor: AlwaysStoppedAnimation<Color>(acento),
                    ),
                  ),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              CifraAnimada(
                valor: puntaje,
                sufijo: ' %',
                estilo: Cifras.heroe(context).copyWith(color: acento),
              ),
              Text(
                '${resultado.correctas}/${resultado.total}',
                style: Cifras.pequena(context),
              ),
            ],
          ),
        ],
      ),
    );

    return Column(
      children: <Widget>[
        Semantics(
          label: 'Puntaje $puntaje por ciento, ${resultado.correctas} '
              'correctas de ${resultado.total}',
          child: ExcludeSemantics(
            child: quieto
                ? anillo
                : anillo.animate().fadeIn(duration: Movimiento.corta),
          ),
        ),
        const SizedBox(height: Espacio.md),
        Text(
          aprobo ? 'DESAFÍO SUPERADO' : 'AÚN NO',
          style: context.textos.labelSmall?.copyWith(color: acento),
        ),
        const SizedBox(height: Espacio.xxs),
        Text(
          aprobo
              ? resultado.resultado.etiqueta
              : 'Reforcemos un par de temas y vuelve a intentarlo',
          textAlign: TextAlign.center,
          style: context.textos.headlineSmall,
        ),
        const SizedBox(height: Espacio.sm),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            if (resultado.puntaje >= 90 && resultado.puntaje < 100)
              const Pildora(
                texto: 'Estrella extra',
                icono: Icons.star_rounded,
              ),
            if (resultado.puntaje >= 100)
              Pildora(
                texto: 'Sin fallas',
                icono: Icons.workspace_premium_rounded,
                color: p.oro,
              ),
            Pildora(
              texto: 'Se supera con ${resultado.puntajeAprobacion.round()} %',
              icono: Icons.flag_outlined,
            ),
          ],
        ),
      ],
    );
  }
}

/// Una fila del desglose por tema, con su barra y su atajo a repaso.
class _FilaTema extends StatelessWidget {
  const _FilaTema({required this.tema});

  final PuntajeTema tema;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final Color color = tema.esDebil ? p.advertencia : p.exito;

    return Padding(
      padding: const EdgeInsets.only(bottom: Espacio.xs),
      child: TarjetaAtenea(
        padding: const EdgeInsets.all(Espacio.sm),
        semantica: '${tema.titulo}: ${tema.correctas} de ${tema.total} '
            'correctas',
        hijo: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(
                  tema.esDebil
                      ? Icons.trending_down_rounded
                      : Icons.check_circle_outline_rounded,
                  size: 18,
                  color: color,
                ),
                const SizedBox(width: Espacio.xs),
                Expanded(
                  child: Text(
                    tema.titulo.isEmpty ? 'Tema' : tema.titulo,
                    style: context.textos.bodyLarge,
                  ),
                ),
                ExcludeSemantics(
                  child: Text(
                    '${tema.correctas}/${tema.total}',
                    style: Cifras.pequena(context).copyWith(color: color),
                  ),
                ),
              ],
            ),
            const SizedBox(height: Espacio.xs),
            BarraProgreso(valor: tema.fraccion, color: color, alto: 8),
            if (tema.esDebil && tema.temaId.isNotEmpty)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: () => context.go(Rutas.repaso(tema.temaId)),
                  icon: const Icon(Icons.refresh_rounded, size: 18),
                  label: const Text('Repasar este tema'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Recordatorio de que nada se pierde por no superarlo.
class _NotaSinCastigo extends StatelessWidget {
  const _NotaSinCastigo({required this.enfriamiento, required this.umbral});

  final DateTime? enfriamiento;
  final double umbral;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final DateTime? hasta = enfriamiento;
    final bool descansando = hasta != null && hasta.isAfter(DateTime.now());

    return TarjetaAtenea(
      hijo: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(Icons.shield_moon_outlined, color: p.info),
          const SizedBox(width: Espacio.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Nada se pierde', style: context.textos.titleMedium),
                const SizedBox(height: Espacio.xxs),
                Text(
                  'Tu dominio se actualizó con lo que demostraste hoy y tu '
                  'progreso del módulo sigue intacto. Solo falta llegar al '
                  '${umbral.round()} %.',
                  style: context.textos.bodyMedium?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
                if (descansando) ...<Widget>[
                  const SizedBox(height: Espacio.xs),
                  Pildora(
                    texto: 'Nuevo intento disponible más tarde',
                    icono: Icons.hourglass_bottom_rounded,
                    color: p.info,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Revisión pregunta a pregunta
// ---------------------------------------------------------------------------

class _HojaRevision extends StatefulWidget {
  const _HojaRevision({required this.revision});

  final RevisionEvaluacion revision;

  @override
  State<_HojaRevision> createState() => _HojaRevisionState();
}

class _HojaRevisionState extends State<_HojaRevision> {
  bool _soloFalladas = false;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final List<RespuestaRevisada> lista = _soloFalladas
        ? widget.revision.falladas
        : widget.revision.respuestas;

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
                Expanded(
                  child: Text(
                    'Revisar respuestas',
                    style: context.textos.headlineSmall,
                  ),
                ),
                Text(
                  '${widget.revision.falladas.length} por afinar',
                  style: context.textos.bodySmall?.copyWith(
                    color: p.textoSecundario,
                  ),
                ),
              ],
            ),
            const SizedBox(height: Espacio.xs),
            Align(
              alignment: Alignment.centerLeft,
              child: FilterChip(
                selected: _soloFalladas,
                label: const Text('Solo las que fallé'),
                onSelected: (bool v) => setState(() => _soloFalladas = v),
              ),
            ),
            const SizedBox(height: Espacio.sm),
            Flexible(
              child: lista.isEmpty
                  ? const EstadoVacio(
                      icono: Icons.celebration_outlined,
                      titulo: 'Ni una sola falla',
                      mensaje: 'Respondiste todo correctamente. Impecable.',
                    )
                  : ListView.separated(
                      shrinkWrap: true,
                      itemCount: lista.length,
                      separatorBuilder: (BuildContext contexto, int indice) =>
                          const SizedBox(height: Espacio.xs),
                      itemBuilder: (BuildContext contexto, int indice) =>
                          _FichaRevision(
                        respuesta: lista[indice],
                        numero: indice + 1,
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FichaRevision extends StatelessWidget {
  const _FichaRevision({required this.respuesta, required this.numero});

  final RespuestaRevisada respuesta;
  final int numero;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool bien = respuesta.esCorrecta;
    final Color color = bien ? p.exito : p.advertencia;
    final String correcta = _texto(respuesta.respuestaCorrecta);
    final String dada = _texto(respuesta.respuesta);

    return TarjetaAtenea(
      padding: EdgeInsets.zero,
      hijo: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          shape: const RoundedRectangleBorder(borderRadius: Redondeo.rTarjeta),
          collapsedShape:
              const RoundedRectangleBorder(borderRadius: Redondeo.rTarjeta),
          leading: Icon(
            bien ? Icons.check_circle_rounded : Icons.info_rounded,
            color: color,
          ),
          title: Text(
            respuesta.pregunta.enunciado,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: context.textos.bodyLarge,
          ),
          subtitle: Text(
            '$numero · ${respuesta.resultado.etiqueta}',
            style: context.textos.bodySmall?.copyWith(color: color),
          ),
          childrenPadding: const EdgeInsets.fromLTRB(
            Espacio.md,
            0,
            Espacio.md,
            Espacio.md,
          ),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (dada.isNotEmpty)
              FilaDato(
                etiqueta: 'Tu respuesta',
                valor: dada,
                icono: Icons.person_outline_rounded,
              ),
            if (correcta.isNotEmpty)
              FilaDato(
                etiqueta: 'La correcta',
                valor: correcta,
                icono: Icons.check_rounded,
              ),
            if ((respuesta.explicacion ?? '').isNotEmpty) ...<Widget>[
              const SizedBox(height: Espacio.xs),
              TextoRico(texto: respuesta.explicacion!),
            ],
            if (respuesta.procedencia.isNotEmpty)
              ChipFuente(procedencia: respuesta.procedencia),
          ],
        ),
      ),
    );
  }

  static String _texto(Object? valor) {
    if (valor == null) return '';
    if (valor is String) return valor;
    if (valor is List) {
      return valor.map((Object? e) => e?.toString() ?? '').join(', ');
    }
    if (valor is Map) {
      return valor.entries
          .map(
            (MapEntry<Object?, Object?> e) => '${e.key} → ${e.value}',
          )
          .join(' · ');
    }
    return valor.toString();
  }
}
