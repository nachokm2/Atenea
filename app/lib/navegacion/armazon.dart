/// Armazón de la aplicación: la barra inferior de cuatro destinos y la capa
/// donde se muestran las celebraciones encoladas.
///
/// Reglas de §3.3 del documento de UX que se cumplen aquí:
///
/// - La barra inferior solo existe dentro de este armazón, es decir, en los
///   cuatro destinos raíz y en sus pantallas de lista (Misiones, Mercado,
///   Vestidor, Racha, Logros y Ajustes). Los flujos inmersivos —lección,
///   desafío, crear ruta y generación— viven fuera y se cierran con una X.
/// - Las celebraciones se pintan por **encima de cualquier pantalla**: por eso
///   [CapaCelebraciones] se instala en `app.dart`, envolviendo al enrutador
///   entero, y no solo dentro del armazón.
/// - Los detalles (fuente de un bloque, ficha de ítem, confirmación de compra)
///   se abren con [mostrarHoja], nunca como pantalla nueva.
library;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../design/components.dart';
import '../design/tokens.dart';
import '../estado/celebraciones.dart';

/// Los cuatro destinos de la barra inferior, en su orden visual.
enum DestinoRaiz {
  inicio('Inicio', Icons.home_outlined, Icons.home_rounded),
  aventura('Aventura', Icons.explore_outlined, Icons.explore_rounded),
  personaje('Personaje', Icons.checkroom_outlined, Icons.checkroom_rounded),
  perfil('Perfil', Icons.auto_stories_outlined, Icons.auto_stories_rounded);

  const DestinoRaiz(this.etiqueta, this.icono, this.iconoActivo);

  /// Nombre visible y etiqueta del lector de pantalla.
  final String etiqueta;

  /// Icono en reposo.
  final IconData icono;

  /// Icono del destino activo.
  final IconData iconoActivo;
}

/// Armazón con la barra inferior de cuatro destinos.
class ArmazonAtenea extends StatelessWidget {
  const ArmazonAtenea({required this.navegacion, super.key});

  /// Cáscara de `go_router` que conserva el estado de cada rama.
  final StatefulNavigationShell navegacion;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    return Scaffold(
      backgroundColor: paleta.fondo,
      body: navegacion,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navegacion.currentIndex,
        onDestinationSelected: (int indice) => navegacion.goBranch(
          indice,
          // Volver a tocar el destino activo lleva a su raíz.
          initialLocation: indice == navegacion.currentIndex,
        ),
        destinations: <Widget>[
          for (final DestinoRaiz destino in DestinoRaiz.values)
            NavigationDestination(
              icon: Icon(destino.icono),
              selectedIcon: Icon(destino.iconoActivo),
              label: destino.etiqueta,
              tooltip: destino.etiqueta,
            ),
        ],
      ),
    );
  }
}

/// Abre un detalle como hoja inferior (§3.3 regla 4).
Future<T?> mostrarHoja<T>(
  BuildContext context, {
  required Widget Function(BuildContext context) constructor,
  bool ajustable = true,
}) {
  final AteneaPalette paleta = context.paleta;
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: ajustable,
    useSafeArea: true,
    backgroundColor: paleta.superficieElevada,
    shape: const RoundedRectangleBorder(borderRadius: Redondeo.rHoja),
    builder: constructor,
  );
}

/// Capa que pinta la celebración encolada por encima de todo.
///
/// Se instala una sola vez, en `app.dart`, para que también cubra los flujos
/// inmersivos (P10 y P12 encolan celebraciones fuera del armazón).
class CapaCelebraciones extends StatefulWidget {
  const CapaCelebraciones({required this.hijo, super.key, this.constructor});

  /// Toda la aplicación.
  final Widget hijo;

  /// Permite a las pantallas P13 y P14 sustituir la presentación por defecto.
  /// Recibe la celebración y la acción que la cierra.
  final Widget Function(
    BuildContext context,
    Celebracion celebracion,
    VoidCallback cerrar,
  )? constructor;

  @override
  State<CapaCelebraciones> createState() => _CapaCelebracionesState();
}

class _CapaCelebracionesState extends State<CapaCelebraciones> {
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sincronizarMovimiento();
  }

  /// Mantiene la cola al tanto de la preferencia de movimiento reducido.
  /// Se aplaza al final del fotograma porque el ajuste notifica oyentes.
  void _sincronizarMovimiento() {
    final bool reducir = reducirMovimiento(context);
    final ColaCelebraciones cola = context.read<ColaCelebraciones>();
    if (cola.movimientoReducido == reducir) return;
    WidgetsBinding.instance.addPostFrameCallback((Duration _) {
      if (!mounted) return;
      cola.movimientoReducido = reducir;
    });
  }

  @override
  Widget build(BuildContext context) {
    final ColaCelebraciones cola = context.watch<ColaCelebraciones>();
    final Celebracion? actual = cola.actual;
    return Stack(
      children: <Widget>[
        widget.hijo,
        if (actual != null)
          // TODO(pantalla): P13/P14 — pasar `constructor` con
          // ModalSubidaDeNivel (lib/pantallas/celebraciones/modal_nivel.dart)
          // y ModalItemDesbloqueado
          // (lib/pantallas/celebraciones/modal_item.dart).
          widget.constructor?.call(context, actual, cola.descartar) ??
              _OverlayCelebracion(
                celebracion: actual,
                listaParaContinuar: cola.listaParaContinuar,
                alSaltar: cola.saltarAnimacion,
                alCerrar: cola.descartar,
              ),
      ],
    );
  }
}

/// Presentación provisional de una celebración, con versión estática cuando
/// el sistema pide reducir movimiento.
class _OverlayCelebracion extends StatelessWidget {
  const _OverlayCelebracion({
    required this.celebracion,
    required this.listaParaContinuar,
    required this.alSaltar,
    required this.alCerrar,
  });

  final Celebracion celebracion;
  final bool listaParaContinuar;
  final VoidCallback alSaltar;
  final VoidCallback alCerrar;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette paleta = context.paleta;
    final bool quieto = reducirMovimiento(context);
    final Duration entrada = quieto ? Duration.zero : Movimiento.corta;
    final Color acento = switch (celebracion.paso) {
      PasoCelebracion.racha => paleta.brasa,
      PasoCelebracion.subidaNivel => paleta.arcano,
      PasoCelebracion.item => celebracion.rarezaVisual.color,
      _ => paleta.oro,
    };

    return Semantics(
      liveRegion: true,
      label: celebracion.semantica,
      child: Material(
        color: paleta.fondo.withValues(alpha: 0.92),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          // Un toque salta la animación; si ya terminó, cierra.
          onTap: listaParaContinuar ? alCerrar : alSaltar,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: Medida.lecturaMax),
              child: Padding(
                padding: const EdgeInsets.all(Espacio.lg),
                child: AnimatedScale(
                  scale: 1,
                  duration: entrada,
                  curve: Movimiento.entrada,
                  child: TarjetaAtenea(
                    elevada: true,
                    colorBorde: acento,
                    brillo: quieto ? 0 : celebracion.rarezaVisual.brillo,
                    hijo: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Icon(
                          _icono(celebracion.paso),
                          size: Tipo.heroe,
                          color: acento,
                        ),
                        const SizedBox(height: Espacio.md),
                        Text(
                          celebracion.paso.etiqueta.toUpperCase(),
                          textAlign: TextAlign.center,
                          style: context.textos.labelMedium?.copyWith(
                            color: paleta.textoSecundario,
                          ),
                        ),
                        const SizedBox(height: Espacio.xs),
                        Text(
                          celebracion.titulo,
                          textAlign: TextAlign.center,
                          style: context.textos.headlineSmall,
                        ),
                        if (celebracion.detalle != null) ...<Widget>[
                          const SizedBox(height: Espacio.xs),
                          Text(
                            celebracion.detalle!,
                            textAlign: TextAlign.center,
                            style: context.textos.bodyMedium?.copyWith(
                              color: paleta.textoSecundario,
                            ),
                          ),
                        ],
                        const SizedBox(height: Espacio.lg),
                        BotonPrimario(
                          texto: celebracion.textoAccion,
                          alTocar: alCerrar,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  static IconData _icono(PasoCelebracion paso) => switch (paso) {
        PasoCelebracion.racha => Icons.local_fire_department_rounded,
        PasoCelebracion.subidaNivel => Icons.shield_rounded,
        PasoCelebracion.item => Icons.auto_awesome_rounded,
        PasoCelebracion.logro => Icons.military_tech_rounded,
        PasoCelebracion.mision => Icons.flag_rounded,
        PasoCelebracion.xp => Icons.auto_awesome_rounded,
        PasoCelebracion.oro => Icons.monetization_on_rounded,
        PasoCelebracion.dominio => Icons.psychology_rounded,
      };
}
