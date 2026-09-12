/// P07 · Mapa de la ruta.
///
/// El camino completo de un territorio: módulos, lecciones y el Desafío del
/// módulo, con bloqueo progresivo visible y motivador. Al final del sendero
/// espera el tesoro de la Ruta.
///
/// Estados cubiertos: carga con esqueleto del camino, error con caché y
/// reintento, ruta parcial (módulos todavía en construcción), temas cubiertos
/// con el saber del Reino, esquema pendiente de confirmar y ruta completada.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../data/errores.dart';
import '../../datos/repositorios.dart';
import '../../design/components.dart';
import '../../design/tokens.dart';
import '../../estado/aventura.dart';
import '../../navegacion/rutas.dart';
import 'widgets/comunes_aventura.dart';
import 'widgets/hojas_aventura.dart';
import 'widgets/nodos_mapa.dart';

/// Pantalla del mapa de una Ruta.
class PantallaMapaRuta extends StatefulWidget {
  const PantallaMapaRuta({required this.rutaId, super.key});

  /// Ruta que se está recorriendo.
  final String rutaId;

  @override
  State<PantallaMapaRuta> createState() => _PantallaMapaRutaState();
}

class _PantallaMapaRutaState extends State<PantallaMapaRuta> {
  /// Módulos que el usuario abrió o cerró a mano; el resto sigue la regla
  /// "el módulo actual viene abierto".
  final Map<String, bool> _plegados = <String, bool>{};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<ControladorAventura>().abrirRuta(widget.rutaId);
    });
  }

  // ---------------------------------------------------------------------
  // Reglas de presentación
  // ---------------------------------------------------------------------

  bool _expandido(DetalleRuta detalle, ModuloRuta modulo) =>
      _plegados[modulo.id] ?? (detalle.moduloActual?.id == modulo.id);

  EstiloNodo _estiloModulo(DetalleRuta detalle, ModuloRuta modulo) {
    if (modulo.estado == EstadoModulo.completado ||
        modulo.estado == EstadoModulo.dominado) {
      return EstiloNodo.completado;
    }
    if (modulo.estaBloqueado) return EstiloNodo.bloqueado;
    if (modulo.enConstruccion) return EstiloNodo.enConstruccion;
    if (detalle.moduloActual?.id == modulo.id) return EstiloNodo.actual;
    return EstiloNodo.disponible;
  }

  EstiloNodo _estiloLeccion(
    ModuloRuta modulo,
    ResumenLeccion leccion, {
    required bool esSiguiente,
  }) {
    if (leccion.estaCompletada) return EstiloNodo.completado;
    if (modulo.estaBloqueado) return EstiloNodo.bloqueado;
    if (!leccion.estaLista) return EstiloNodo.enConstruccion;
    return esSiguiente ? EstiloNodo.actual : EstiloNodo.disponible;
  }

  EstiloNodo _estiloDesafio(ModuloRuta modulo, ResumenEvaluacion evaluacion) {
    if (evaluacion.aprobada) return EstiloNodo.completado;
    if (modulo.estaBloqueado) return EstiloNodo.bloqueado;
    if (!evaluacion.estadoContenido.estaDisponible) {
      return EstiloNodo.enConstruccion;
    }
    if (!evaluacion.puedeEmpezar) return EstiloNodo.bloqueado;
    final bool listasTodas = modulo.leccionesTotales > 0 &&
        modulo.leccionesCompletadas >= modulo.leccionesTotales;
    return listasTodas ? EstiloNodo.actual : EstiloNodo.disponible;
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

  void _tocarModulo(DetalleRuta detalle, ModuloRuta modulo) {
    if (modulo.estaBloqueado) {
      explicarBloqueo(
        context,
        titulo: modulo.nombreVisible,
        mensaje: modulo.motivoBloqueo ??
            'Este módulo se abre cuando completes el anterior.',
        consejo: 'Cada zona que superas desbloquea la siguiente: así el camino '
            'siempre está a tu medida.',
      );
      return;
    }
    if (modulo.enConstruccion) {
      explicarBloqueo(
        context,
        titulo: modulo.nombreVisible,
        mensaje: 'El Reino todavía está escribiendo este módulo.',
        consejo: 'Te avisamos en cuanto esté listo. Mientras tanto puedes '
            'avanzar en los módulos abiertos.',
      );
      return;
    }
    setState(() => _plegados[modulo.id] = !_expandido(detalle, modulo));
  }

  Future<void> _tocarLeccion(
    ModuloRuta modulo,
    ResumenLeccion leccion,
    EstiloNodo estilo,
  ) async {
    switch (estilo) {
      case EstiloNodo.bloqueado:
        await explicarBloqueo(
          context,
          titulo: leccion.titulo,
          mensaje: modulo.motivoBloqueo ??
              'Completa el módulo anterior para llegar hasta aquí.',
        );
      case EstiloNodo.enConstruccion:
        await explicarBloqueo(
          context,
          titulo: leccion.titulo,
          mensaje: 'Esta lección se está escribiendo ahora mismo.',
          consejo: 'Vuelve en unos minutos: te avisamos cuando esté lista.',
        );
      case EstiloNodo.completado:
        final bool repasar = await confirmarAccion(
          context,
          titulo: '¿Repasar esta lección?',
          mensaje: 'Ya la completaste. Al repetirla no ganas XP de lección, '
              'pero sí de las preguntas nuevas, y tu dominio se refuerza.',
          textoConfirmar: 'Repasar',
          textoCancelar: 'Ahora no',
          destructiva: false,
        );
        if (!mounted || !repasar) return;
        context.push(Rutas.leccion(leccion.id));
      case EstiloNodo.actual:
      case EstiloNodo.disponible:
        context.push(Rutas.leccion(leccion.id));
    }
  }

  Future<void> _tocarDesafio(
    ModuloRuta modulo,
    ResumenEvaluacion evaluacion,
    EstiloNodo estilo,
  ) async {
    if (estilo == EstiloNodo.enConstruccion) {
      await explicarBloqueo(
        context,
        titulo: 'Desafío del módulo',
        mensaje: 'El Reino prepara las preguntas de este desafío.',
      );
      return;
    }
    if (estilo == EstiloNodo.bloqueado) {
      await explicarBloqueo(
        context,
        titulo: 'Desafío del módulo',
        mensaje: evaluacion.enEnfriamiento
            ? 'Acabas de intentarlo. Dale un momento al Reino para preparar '
                'preguntas distintas.'
            : 'Completa las lecciones de ${modulo.nombreVisible} para '
                'presentarte al desafío.',
        consejo: 'Nada se pierde: el desafío se puede repetir.',
      );
      return;
    }
    context.push(Rutas.evaluacion(modulo.id));
  }

  Future<void> _menu(ResumenRuta ruta) async {
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final AccionRuta? accion = await menuDeRuta(
      context,
      titulo: ruta.titulo.isEmpty ? 'Ruta sin nombre' : ruta.titulo,
      archivada: ruta.archivadaEn != null,
      puedeEliminar: !ruta.esDelReino,
    );
    if (!mounted || accion == null) return;

    switch (accion) {
      case AccionRuta.renombrar:
        final String? nuevo =
            await pedirNuevoTitulo(context, actual: ruta.titulo);
        if (!mounted || nuevo == null) return;
        final bool bien = await aventura.actualizarRuta(ruta.id, titulo: nuevo);
        _avisar(bien
            ? 'Tu territorio ahora se llama "$nuevo".'
            : 'No pudimos cambiar el nombre. Inténtalo otra vez.');
      case AccionRuta.fuentes:
        await mostrarFuentes(context, ruta.id);
      case AccionRuta.archivar:
        final bool bien =
            await aventura.actualizarRuta(ruta.id, archivada: true);
        _avisar(bien
            ? 'Guardamos la ruta en tu archivo.'
            : 'No pudimos archivarla. Inténtalo otra vez.');
      case AccionRuta.desarchivar:
        final bool bien =
            await aventura.actualizarRuta(ruta.id, archivada: false);
        _avisar(bien
            ? 'La ruta vuelve a tus territorios.'
            : 'No pudimos recuperarla. Inténtalo otra vez.');
      case AccionRuta.eliminar:
        final bool seguro = await confirmarAccion(
          context,
          titulo: '¿Eliminar esta ruta?',
          mensaje: 'Se borra el camino y sus misiones. Tu XP, tu oro y tu '
              'dominio se quedan contigo.',
          textoConfirmar: 'Eliminar',
        );
        if (!mounted || !seguro) return;
        final bool bien = await aventura.eliminarRuta(ruta.id);
        if (!mounted) return;
        if (bien) {
          context.go(Rutas.aventura);
        } else {
          _avisar('No pudimos eliminarla. Inténtalo otra vez.');
        }
    }
  }

  Future<void> _confirmarEsquema(DetalleRuta detalle) async {
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final bool bien = await aventura.confirmarEsquema(
      widget.rutaId,
      politicaCobertura: detalle.ruta.politicaCobertura,
    );
    if (!mounted) return;
    _avisar(bien
        ? 'Esquema confirmado. El Reino empieza a escribir el Módulo 1.'
        : (aventura.errorRuta?.mensaje ??
            'No pudimos confirmar el esquema. Inténtalo otra vez.'));
    if (bien) context.push(Rutas.generacion(widget.rutaId));
  }

  // ---------------------------------------------------------------------
  // Construcción
  // ---------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorAventura aventura = context.watch<ControladorAventura>();
    final DetalleRuta? detalle =
        aventura.ruta?.id == widget.rutaId ? aventura.ruta : null;
    final ErrorAtenea? error = aventura.errorRuta;

    if (detalle == null) {
      return PantallaAtenea(
        titulo: 'Mapa de la ruta',
        mostrarVolver: true,
        cuerpo: aventura.cargandoRuta
            ? const _EsqueletoCamino()
            : EstadoError(
                titulo: 'No pudimos abrir el mapa',
                mensaje: error?.mensaje ??
                    'El camino no aparece por ninguna parte. Inténtalo otra vez.',
                alReintentar: () =>
                    aventura.abrirRuta(widget.rutaId, forzar: true),
              ),
      );
    }

    final ResumenRuta ruta = detalle.ruta;

    return PantallaAtenea(
      titulo: ruta.titulo.isEmpty ? 'Mapa de la ruta' : ruta.titulo,
      mostrarVolver: true,
      padding: EdgeInsets.zero,
      acciones: <Widget>[
        IconButton(
          onPressed: () => mostrarFuentes(context, widget.rutaId),
          icon: const Icon(Icons.source_outlined),
          tooltip: 'Material de la ruta',
        ),
        IconButton(
          onPressed: () => _menu(ruta),
          icon: const Icon(Icons.more_vert_rounded),
          tooltip: 'Opciones de la ruta',
        ),
      ],
      cuerpo: RefreshIndicator(
        onRefresh: () => aventura.abrirRuta(widget.rutaId, forzar: true),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            Espacio.md,
            Espacio.xs,
            Espacio.md,
            Espacio.xxl,
          ),
          children: <Widget>[
            _Cabecera(ruta: ruta),
            if (error != null) ...<Widget>[
              const SizedBox(height: Espacio.sm),
              FranjaEstado(
                icono: Icons.cloud_off_rounded,
                color: context.paleta.advertencia,
                mensaje: 'Te mostramos el último mapa guardado.',
                textoAccion: 'Actualizar',
                alTocarAccion: () =>
                    aventura.abrirRuta(widget.rutaId, forzar: true),
              ),
            ],
            ..._avisosDelMapa(detalle),
            const SizedBox(height: Espacio.md),
            ..._camino(detalle),
          ],
        ),
      ),
    );
  }

  List<Widget> _avisosDelMapa(DetalleRuta detalle) {
    final AteneaPalette p = context.paleta;
    final ResumenRuta ruta = detalle.ruta;
    final bool hayConocimientoGeneral = detalle.avisosCobertura.isNotEmpty ||
        detalle.modulos.any(
          (ModuloRuta m) => m.temas.any((Tema t) => t.esConocimientoGeneral),
        );

    return <Widget>[
      if (detalle.puedeConfirmar) ...<Widget>[
        const SizedBox(height: Espacio.sm),
        TarjetaAviso(
          icono: Icons.fact_check_outlined,
          color: p.arcano,
          titulo: 'Revisa el esquema antes de forjar',
          mensaje: 'Este es el plan que propone el Reino. Si te convence, '
              'confírmalo y empezamos a escribir el Módulo 1.',
          textoAccion: 'Confirmar el esquema',
          alTocarAccion: () => _confirmarEsquema(detalle),
        ),
      ],
      if (ruta.estaGenerando && !detalle.puedeConfirmar) ...<Widget>[
        const SizedBox(height: Espacio.sm),
        FranjaEstado(
          icono: Icons.local_fire_department_rounded,
          color: p.info,
          mensaje: 'Todavía se están forjando módulos de esta ruta.',
          textoAccion: 'Ver avance',
          alTocarAccion: () => context.push(Rutas.generacion(widget.rutaId)),
        ),
      ],
      if (hayConocimientoGeneral) ...<Widget>[
        const SizedBox(height: Espacio.sm),
        FranjaEstado(
          icono: Icons.auto_stories_rounded,
          color: p.info,
          mensaje: 'Algunos temas se explican con el saber del Reino: van '
              'marcados en el camino y en la lección.',
        ),
      ],
    ];
  }

  List<Widget> _camino(DetalleRuta detalle) {
    final List<Widget> nodos = <Widget>[];
    final List<ModuloRuta> modulos = detalle.modulos;

    if (modulos.isEmpty) {
      return <Widget>[
        EstadoVacio(
          icono: Icons.map_outlined,
          titulo: 'El camino aún no está trazado',
          mensaje: 'El Reino todavía no ha dibujado los módulos de esta ruta.',
          textoAccion: 'Ver el avance de la forja',
          alTocarAccion: () => context.push(Rutas.generacion(widget.rutaId)),
        ),
      ];
    }

    int indice = 0;
    for (int i = 0; i < modulos.length; i++) {
      final ModuloRuta modulo = modulos[i];
      final EstiloNodo estilo = _estiloModulo(detalle, modulo);
      final bool hecho = estilo == EstiloNodo.completado;
      final bool anteriorHecho = i == 0
          ? false
          : _estiloModulo(detalle, modulos[i - 1]) == EstiloNodo.completado;
      final bool abierto = _expandido(detalle, modulo);
      final List<ResumenLeccion> lecciones = modulo.todasLasLecciones;
      final ResumenLeccion? siguiente = _primeraPendiente(lecciones);

      nodos.add(
        AparecerEnCascada(
          indice: indice++,
          hijo: NodoCamino(
            estilo: estilo,
            grande: true,
            lineaArriba: i > 0,
            tramoSuperiorHecho: anteriorHecho,
            tramoInferiorHecho: hecho,
            icono: estilo == EstiloNodo.completado
                ? Icons.check_rounded
                : (estilo == EstiloNodo.bloqueado
                    ? Icons.lock_rounded
                    : Icons.castle_rounded),
            hijo: ContenidoModulo(
              modulo: modulo,
              estilo: estilo,
              expandido: abierto,
              alTocar: () => _tocarModulo(detalle, modulo),
            ),
          ),
        ),
      );

      if (!abierto) continue;

      for (final ResumenLeccion leccion in lecciones) {
        final EstiloNodo estiloLeccion = _estiloLeccion(
          modulo,
          leccion,
          esSiguiente: siguiente?.id == leccion.id,
        );
        nodos.add(
          AparecerEnCascada(
            indice: indice++,
            hijo: NodoCamino(
              estilo: estiloLeccion,
              sangria: Espacio.md,
              tramoSuperiorHecho: hecho,
              tramoInferiorHecho: hecho,
              hijo: ContenidoLeccion(
                leccion: leccion,
                estilo: estiloLeccion,
                alTocar: () => _tocarLeccion(modulo, leccion, estiloLeccion),
              ),
            ),
          ),
        );
      }

      final ResumenEvaluacion? evaluacion = modulo.evaluacion;
      if (evaluacion != null) {
        final EstiloNodo estiloDesafio = _estiloDesafio(modulo, evaluacion);
        nodos.add(
          AparecerEnCascada(
            indice: indice++,
            hijo: NodoCamino(
              estilo: estiloDesafio,
              sangria: Espacio.xs,
              icono: Icons.shield_rounded,
              tramoSuperiorHecho: hecho,
              tramoInferiorHecho: hecho,
              hijo: ContenidoDesafio(
                evaluacion: evaluacion,
                estilo: estiloDesafio,
                alTocar: () => _tocarDesafio(modulo, evaluacion, estiloDesafio),
              ),
            ),
          ),
        );
      }
    }

    final bool completada = detalle.ruta.estado == EstadoRuta.completada;
    nodos.add(
      AparecerEnCascada(
        indice: indice,
        hijo: NodoCamino(
          estilo: completada ? EstiloNodo.completado : EstiloNodo.bloqueado,
          grande: true,
          lineaAbajo: false,
          tramoSuperiorHecho: completada,
          icono: completada
              ? Icons.emoji_events_rounded
              : Icons.workspace_premium_outlined,
          hijo: ContenidoTesoro(
            completada: completada,
            item: detalle.itemDeConocimiento,
          ),
        ),
      ),
    );

    return nodos;
  }

  ResumenLeccion? _primeraPendiente(List<ResumenLeccion> lecciones) {
    for (final ResumenLeccion leccion in lecciones) {
      if (!leccion.estaCompletada && leccion.estaLista) return leccion;
    }
    return null;
  }
}

// -------------------------------------------------------------------------
// Piezas
// -------------------------------------------------------------------------

/// Cabecera del territorio: emblema, cifras del avance y barra general.
class _Cabecera extends StatelessWidget {
  const _Cabecera({required this.ruta});

  final ResumenRuta ruta;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool completada = ruta.estado == EstadoRuta.completada;
    final Color acento = colorDesdeHex(ruta.colorAcento) ?? p.arcano;

    return TarjetaAtenea(
      elevada: true,
      colorBorde: completada ? p.oro.withValues(alpha: 0.6) : null,
      brillo: completada ? 10 : null,
      hijo: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              EmblemaTerritorio(
                nombre: ruta.nombreConocimiento ?? ruta.titulo,
                iconoKey: ruta.iconoKey,
                colorAcento: ruta.colorAcento,
                tamano: 58,
                resplandor: completada,
              ),
              const SizedBox(width: Espacio.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      ruta.nombreConocimiento ?? 'Territorio del Reino',
                      style: context.textos.labelSmall
                          ?.copyWith(color: p.textoSecundario),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      ruta.titulo.isEmpty ? 'Ruta sin nombre' : ruta.titulo,
                      style: context.textos.headlineSmall,
                    ),
                    const SizedBox(height: Espacio.xs),
                    Wrap(
                      spacing: Espacio.xs,
                      runSpacing: Espacio.xxs,
                      children: <Widget>[
                        Pildora(
                          texto: ruta.estado.etiqueta,
                          icono: iconoDeEstadoRuta(ruta.estado),
                          color: colorDeEstadoRuta(context, ruta.estado),
                        ),
                        Pildora(
                          texto: ruta.nivelDeclarado.etiqueta,
                          icono: Icons.signal_cellular_alt_rounded,
                          color: p.textoSecundario,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: Espacio.md),
          BarraProgreso(
            valor: ruta.porcentajeAvance / 100,
            color: completada ? p.oro : acento,
            etiqueta: 'Módulos ${ruta.modulosCompletados}/${ruta.modulos}',
            textoDerecha: porcentajeLegible(ruta.porcentajeAvance),
          ),
          const SizedBox(height: Espacio.sm),
          Row(
            children: <Widget>[
              FichaMedallon(
                tipo: Medallon.dominio,
                valor: porcentajeLegible(ruta.dominio),
                etiqueta: 'Dominio del territorio',
                compacto: true,
              ),
              const SizedBox(width: Espacio.md),
              FichaMedallon(
                tipo: Medallon.xp,
                valor: '${ruta.leccionesCompletadas}/${ruta.leccionesTotales}',
                etiqueta: 'Lecciones completadas',
                compacto: true,
              ),
              if (duracionLegible(ruta.minutosEstimados).isNotEmpty) ...<Widget>[
                const SizedBox(width: Espacio.md),
                FichaMedallon(
                  tipo: Medallon.tiempo,
                  valor: duracionLegible(ruta.minutosEstimados),
                  etiqueta: 'Duración estimada',
                  compacto: true,
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

/// Esqueleto del camino mientras llega el mapa.
class _EsqueletoCamino extends StatelessWidget {
  const _EsqueletoCamino();

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: <Widget>[
        TarjetaAtenea(
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Esqueleto(alto: 58, ancho: 58, radio: Redondeo.tarjeta),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Esqueleto(alto: 12, ancho: 90, radio: Redondeo.chip),
                        const SizedBox(height: Espacio.xs),
                        const Esqueleto(alto: 20, ancho: 190),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: Espacio.md),
              const Esqueleto(alto: 10, radio: Redondeo.pildora),
            ],
          ),
        ),
        const SizedBox(height: Espacio.lg),
        for (int i = 0; i < 4; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const SizedBox(
                  width: 48,
                  child: Center(
                    child: Esqueleto(alto: 40, ancho: 40, radio: Redondeo.pildora),
                  ),
                ),
                Expanded(
                  child: TarjetaAtenea(
                    hijo: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        const Esqueleto(alto: 18, ancho: 160),
                        const SizedBox(height: Espacio.xs),
                        Esqueleto(alto: 12, ancho: 110, radio: Redondeo.chip),
                        const SizedBox(height: Espacio.sm),
                        const Esqueleto(alto: 10, radio: Redondeo.pildora),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
