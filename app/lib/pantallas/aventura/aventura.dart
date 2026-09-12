/// P22 · Aventura: mis territorios y las Rutas del Reino.
///
/// Es el "mundo" simplificado del MVP. No hay mapa navegable: cada Ruta es un
/// territorio con su emblema, y la lista de territorios es el mundo.
///
/// Estados cubiertos: primera carga con esqueletos, sin rutas propias (héroe
/// de bienvenida con los dos caminos), rutas forjándose, error con reintento y
/// caché, y scroll infinito sobre mis rutas.
library;

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
import 'widgets/tarjeta_ruta.dart';

/// Pantalla raíz del destino Aventura.
class PantallaAventura extends StatefulWidget {
  const PantallaAventura({super.key});

  @override
  State<PantallaAventura> createState() => _PantallaAventuraState();
}

class _PantallaAventuraState extends State<PantallaAventura> {
  final GlobalKey _claveReino = GlobalKey();

  /// Ruta del Reino que se está adoptando ahora mismo.
  String? _adoptando;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<ControladorAventura>().cargarRutas();
    });
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

  void _abrirRuta(ResumenRuta ruta) {
    if (ruta.estaGenerando) {
      context.push(Rutas.generacion(ruta.id));
      return;
    }
    context.push(Rutas.ruta(ruta.id));
  }

  Future<void> _adoptar(ResumenRuta ruta) async {
    setState(() => _adoptando = ruta.id);
    final ControladorAventura aventura = context.read<ControladorAventura>();
    final ControladorSesion sesion = context.read<ControladorSesion>();
    final DetalleRuta? adoptada = await aventura.adoptar(ruta.id);
    if (!mounted) return;
    setState(() => _adoptando = null);
    if (adoptada == null) {
      _avisar(aventura.errorRutas?.mensaje ??
          'No pudimos abrirte esta ruta. Inténtalo de nuevo.');
      return;
    }
    sesion.anotarRuta();
    if (!mounted) return;
    context.push(Rutas.ruta(adoptada.id));
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
            ? 'Guardamos la ruta. Podrás recuperarla cuando quieras.'
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
        _avisar(bien
            ? 'Ruta eliminada. El territorio vuelve a la bruma.'
            : 'No pudimos eliminarla. Inténtalo otra vez.');
    }
  }

  void _irAlReino() {
    final BuildContext? destino = _claveReino.currentContext;
    if (destino == null) return;
    Scrollable.ensureVisible(
      destino,
      duration: reducirMovimiento(context) ? Duration.zero : Movimiento.transicion,
      curve: Movimiento.estandar,
      alignment: 0.05,
    );
  }

  // ---------------------------------------------------------------------
  // Construcción
  // ---------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final ControladorAventura aventura = context.watch<ControladorAventura>();
    final bool vacioTotal = aventura.mias.isEmpty && aventura.delReino.isEmpty;
    final ErrorAtenea? error = aventura.errorRutas;

    return PantallaAtenea(
      titulo: 'Aventura',
      padding: EdgeInsets.zero,
      acciones: <Widget>[
        IconButton(
          onPressed: () => context.push(Rutas.crearRuta),
          icon: const Icon(Icons.add_circle_outline_rounded),
          tooltip: 'Crear una ruta nueva',
        ),
      ],
      cuerpo: RefreshIndicator(
        onRefresh: () => aventura.cargarRutas(forzar: true),
        child: NotificationListener<ScrollNotification>(
          onNotification: (ScrollNotification aviso) {
            final ScrollMetrics m = aviso.metrics;
            if (m.axis == Axis.vertical &&
                m.pixels > m.maxScrollExtent - 320 &&
                aventura.hayMasMias &&
                !aventura.cargandoMas) {
              aventura.masRutasMias();
            }
            return false;
          },
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              Espacio.md,
              0,
              Espacio.md,
              Espacio.xxl,
            ),
            children: <Widget>[
              if (aventura.cargandoRutas && vacioTotal)
                ..._esqueletos()
              else if (error != null && vacioTotal)
                SizedBox(
                  height: 420,
                  child: EstadoError(
                    titulo: 'El Reino no responde',
                    mensaje: error.mensaje,
                    alReintentar: () => aventura.cargarRutas(forzar: true),
                  ),
                )
              else ...<Widget>[
                if (error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: Espacio.sm),
                    child: FranjaEstado(
                      icono: Icons.cloud_off_rounded,
                      color: context.paleta.advertencia,
                      mensaje: 'Te mostramos lo último que guardamos.',
                      textoAccion: 'Actualizar',
                      alTocarAccion: () => aventura.cargarRutas(forzar: true),
                    ),
                  ),
                ..._misTerritorios(aventura),
                ..._rutasDelReino(aventura),
                ..._porDescubrir(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _esqueletos() => <Widget>[
        const EncabezadoSeccion(titulo: 'Mis territorios'),
        for (int i = 0; i < 2; i++) ...<Widget>[
          const EsqueletoRuta(),
          const SizedBox(height: Espacio.sm),
        ],
        const EncabezadoSeccion(titulo: 'Rutas del Reino'),
        const EsqueletoRuta(),
      ];

  List<Widget> _misTerritorios(ControladorAventura aventura) {
    final List<ResumenRuta> mias = aventura.mias;

    if (aventura.sinRutasPropias) {
      return <Widget>[
        const EncabezadoSeccion(titulo: 'Mis territorios'),
        _HeroeSinRutas(
          alCrear: () => context.push(Rutas.crearRuta),
          alVerElReino: aventura.delReino.isEmpty ? null : _irAlReino,
        ),
      ];
    }

    return <Widget>[
      EncabezadoSeccion(
        titulo: 'Mis territorios',
        subtitulo: mias.length == 1
            ? 'Un camino abierto en el Reino'
            : '${mias.length} caminos abiertos en el Reino',
      ),
      for (int i = 0; i < mias.length; i++) ...<Widget>[
        TarjetaRuta(
          ruta: mias[i],
          indice: i,
          alTocar: () => _abrirRuta(mias[i]),
          alAbrirMenu: () => _menu(mias[i]),
        ),
        const SizedBox(height: Espacio.sm),
      ],
      if (aventura.cargandoMas)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: Espacio.sm),
          child: EsqueletoRuta(),
        ),
      const SizedBox(height: Espacio.xxs),
      SizedBox(
        height: Medida.areaTactilMin,
        child: OutlinedButton.icon(
          onPressed: () => context.push(Rutas.crearRuta),
          icon: const Icon(Icons.add_rounded),
          label: const Text('Crear una ruta nueva'),
        ),
      ),
    ];
  }

  List<Widget> _rutasDelReino(ControladorAventura aventura) {
    final List<ResumenRuta> reino = aventura.delReino;
    return <Widget>[
      Padding(
        key: _claveReino,
        padding: EdgeInsets.zero,
        child: const EncabezadoSeccion(
          titulo: 'Rutas del Reino',
          subtitulo: 'Caminos ya trazados: empiezas a aprender en un toque.',
        ),
      ),
      if (reino.isEmpty)
        TarjetaAtenea(
          hijo: Text(
            'Ahora mismo no hay Rutas del Reino disponibles. Crea la tuya y el '
            'Reino la forjará contigo.',
            style: context.textos.bodyMedium
                ?.copyWith(color: context.paleta.textoSecundario),
          ),
        )
      else
        for (int i = 0; i < reino.length; i++) ...<Widget>[
          TarjetaRutaDelReino(
            ruta: reino[i],
            indice: i,
            adoptando: _adoptando == reino[i].id,
            alTocar: () => context.push(Rutas.ruta(reino[i].id)),
            alEmpezar: () => _adoptar(reino[i]),
          ),
          const SizedBox(height: Espacio.sm),
        ],
    ];
  }

  List<Widget> _porDescubrir() {
    final AteneaPalette p = context.paleta;
    return <Widget>[
      const EncabezadoSeccion(
        titulo: 'Por descubrir',
        subtitulo: 'Territorios en la bruma. Cada ruta que abres ilumina uno.',
      ),
      Row(
        children: <Widget>[
          for (int i = 0; i < 4; i++) ...<Widget>[
            const EmblemaTerritorio(enSilueta: true, tamano: 56),
            if (i < 3) const SizedBox(width: Espacio.sm),
          ],
        ],
      ),
      const SizedBox(height: Espacio.sm),
      Text(
        'El mapa del Reino crece contigo: cuanto más dominas un conocimiento, '
        'más se despeja su territorio.',
        style: context.textos.bodyMedium?.copyWith(color: p.textoSecundario),
      ),
    ];
  }
}

/// Héroe de bienvenida cuando el usuario todavía no tiene ninguna ruta.
class _HeroeSinRutas extends StatelessWidget {
  const _HeroeSinRutas({required this.alCrear, this.alVerElReino});

  final VoidCallback alCrear;
  final VoidCallback? alVerElReino;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      elevada: true,
      colorBorde: p.arcano.withValues(alpha: 0.45),
      hijo: Stack(
        children: <Widget>[
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const EmblemaTerritorio(tamano: 56, iconoKey: 'map'),
                  const SizedBox(width: Espacio.sm),
                  Expanded(
                    child: Text(
                      'Tu mapa está en blanco',
                      style: context.textos.headlineSmall,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: Espacio.sm),
              Text(
                'Elige qué quieres aprender y el Reino trazará el camino: '
                'módulos, lecciones y desafíos hechos a tu medida.',
                style:
                    context.textos.bodyLarge?.copyWith(color: p.textoSecundario),
              ),
              const SizedBox(height: Espacio.md),
              BotonPrimario(
                texto: 'Crear mi primera ruta',
                subtitulo: 'Con tus apuntes o desde cero',
                icono: Icons.auto_awesome_rounded,
                alTocar: alCrear,
              ),
              if (alVerElReino != null) ...<Widget>[
                const SizedBox(height: Espacio.xs),
                SizedBox(
                  height: Medida.areaTactilMin,
                  child: OutlinedButton.icon(
                    onPressed: alVerElReino,
                    icon: const Icon(Icons.shield_moon_rounded),
                    label: const Text('Empezar una Ruta del Reino'),
                  ),
                ),
              ],
            ],
          ),
          Positioned(left: 0, top: 0, child: OrnamentoEsquina(color: p.arcano)),
        ],
      ),
    );
  }
}
