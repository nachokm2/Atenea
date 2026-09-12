/// Galería del sistema de diseño de Atenea — "Crónica luminosa".
///
/// Referencia viva del lenguaje visual: cada token y cada componente se pinta
/// aquí con el mismo código que usan las pantallas reales, de modo que si un
/// token cambia, esta pantalla cambia con él y la desviación se ve al instante.
///
/// Solo está disponible en modo depuración: Ajustes la enlaza bajo
/// "Herramientas del Reino" cuando `kDebugMode` es verdadero.
///
/// Reglas que esta pantalla verifica de un vistazo:
///
/// - Ni un color, tamaño, radio o duración escrito a mano: todo sale de
///   `tokens.dart` (la única excepción, `Colors.transparent`, ni siquiera hace
///   falta aquí).
/// - Los dos temas —Noche del Reino y Día del Reino— con el mismo contenido,
///   conmutables desde la propia galería.
/// - El color nunca es el único portador de significado: rarezas y estados
///   siempre llevan su etiqueta.
/// - Área táctil mínima de 48 dp y escala de texto hasta el 200 %.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../design/components.dart';
import '../design/theme.dart';
import '../design/tokens.dart';
import '../nucleo/controlador_tema.dart';

/// Pantalla de galería del sistema de diseño.
class PantallaGaleriaEstilo extends StatefulWidget {
  const PantallaGaleriaEstilo({super.key});

  @override
  State<PantallaGaleriaEstilo> createState() => _PantallaGaleriaEstiloState();
}

class _PantallaGaleriaEstiloState extends State<PantallaGaleriaEstilo> {
  /// Escala de texto con la que se previsualiza la galería (no afecta al
  /// resto de la aplicación).
  double _escala = 1;

  /// Progreso de ejemplo para barras y cifras: se mueve con el deslizador
  /// para comprobar que nada "baila" al animarse.
  double _avance = 0.62;

  /// Reconstruye las demostraciones animadas.
  int _semilla = 0;

  static const List<double> _escalas = <double>[1.0, 1.3, 2.0];

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool quieto = reducirMovimiento(context);

    return PantallaAtenea(
      titulo: 'Sistema de diseño',
      mostrarVolver: true,
      acciones: <Widget>[
        IconButton(
          tooltip: 'Cambiar entre Noche y Día del Reino',
          onPressed: _alternarTema,
          icon: Icon(
            context.esOscuro
                ? Icons.light_mode_rounded
                : Icons.dark_mode_rounded,
          ),
        ),
      ],
      // `PantallaAtenea` no desplaza su cuerpo: cada pantalla decide cómo se
      // recorre. Aquí la galería entera es una sola columna larga.
      cuerpo: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _Portada(quieto: quieto),
            _Controles(
              escala: _escala,
              escalas: _escalas,
              avance: _avance,
              quieto: quieto,
              alCambiarEscala: (double v) => setState(() => _escala = v),
              alCambiarAvance: (double v) => setState(() => _avance = v),
              alRepetir: () => setState(() => _semilla++),
            ),

            // Todo lo que viene a continuación se pinta con la escala
            // elegida, para auditar el 130 % y el 200 % sin salir de aquí.
            MediaQuery.withClampedTextScaling(
              minScaleFactor: _escala,
              maxScaleFactor: _escala,
              child: Column(
                key: ValueKey<int>(_semilla),
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  const _BloqueColor(),
                  const _BloqueRareza(),
                  const _BloqueTipografia(),
                  _BloqueCifras(avance: _avance),
                  const _BloqueEspacio(),
                  const _BloqueRedondeo(),
                  _BloqueMovimiento(quieto: quieto),
                  const _BloqueMedida(),
                  const _BloqueMedallones(),
                  _BloqueBarras(avance: _avance),
                  const _BloqueTarjetas(),
                  const _BloqueBotones(),
                  const _BloquePiezas(),
                  const _BloqueEstados(),
                ],
              ),
            ),

            const SizedBox(height: Espacio.xl),
            Text(
              'Esta galería es la referencia viva del Reino: si una pantalla '
              'no se parece a lo que ves aquí, la que se equivoca es la '
              'pantalla.',
              textAlign: TextAlign.center,
              style:
                  context.textos.bodySmall?.copyWith(color: p.textoSecundario),
            ),
          ],
        ),
      ),
    );
  }

  void _alternarTema() {
    final ControladorTema tema = context.read<ControladorTema>();
    tema.cambiar(context.esOscuro ? ThemeMode.light : ThemeMode.dark);
  }
}

// ---------------------------------------------------------------------------
// Portada y controles
// ---------------------------------------------------------------------------

class _Portada extends StatelessWidget {
  const _Portada({required this.quieto});

  final bool quieto;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return TarjetaAtenea(
      elevada: true,
      colorBorde: p.oro,
      brillo: quieto ? 0 : 10,
      hijo: Stack(
        children: <Widget>[
          Positioned(
            top: 0,
            right: 0,
            child: OrnamentoEsquina(color: p.oro),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Crónica luminosa', style: context.textos.displaySmall),
              const SizedBox(height: Espacio.xs),
              Text(
                'Un reino nocturno, elegante y limpio donde el conocimiento es '
                'luz. Medieval en la forma, moderno en la ejecución.',
                style: context.textos.bodyLarge?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
              const SizedBox(height: Espacio.md),
              Wrap(
                spacing: Espacio.xs,
                runSpacing: Espacio.xs,
                children: <Widget>[
                  Pildora(
                    texto: context.esOscuro
                        ? 'Noche del Reino'
                        : 'Día del Reino',
                    icono: context.esOscuro
                        ? Icons.nights_stay_rounded
                        : Icons.wb_sunny_rounded,
                    color: p.arcano,
                  ),
                  Pildora(
                    texto: quieto
                        ? 'Movimiento reducido: activo'
                        : 'Movimiento completo',
                    icono: quieto
                        ? Icons.motion_photos_off_rounded
                        : Icons.auto_awesome_motion_rounded,
                    color: quieto ? p.advertencia : p.exito,
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Controles extends StatelessWidget {
  const _Controles({
    required this.escala,
    required this.escalas,
    required this.avance,
    required this.quieto,
    required this.alCambiarEscala,
    required this.alCambiarAvance,
    required this.alRepetir,
  });

  final double escala;
  final List<double> escalas;
  final double avance;
  final bool quieto;
  final ValueChanged<double> alCambiarEscala;
  final ValueChanged<double> alCambiarAvance;
  final VoidCallback alRepetir;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Padding(
      padding: const EdgeInsets.only(top: Espacio.md),
      child: TarjetaAtenea(
        hijo: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Banco de pruebas', style: context.textos.titleMedium),
            const SizedBox(height: Espacio.xs),
            Text(
              'Escala del texto de la galería',
              style: context.textos.bodyMedium?.copyWith(
                color: p.textoSecundario,
              ),
            ),
            const SizedBox(height: Espacio.xs),
            Wrap(
              spacing: Espacio.xs,
              runSpacing: Espacio.xs,
              children: <Widget>[
                for (final double v in escalas)
                  ChoiceChip(
                    selected: escala == v,
                    onSelected: (_) => alCambiarEscala(v),
                    label: Text('${(v * 100).round()} %'),
                  ),
              ],
            ),
            const SizedBox(height: Espacio.sm),
            Text(
              'Progreso de ejemplo: ${(avance * 100).round()} %',
              style: context.textos.bodyMedium?.copyWith(
                color: p.textoSecundario,
              ),
            ),
            Slider(
              value: avance,
              onChanged: alCambiarAvance,
              label: '${(avance * 100).round()} %',
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: alRepetir,
                icon: const Icon(Icons.replay_rounded),
                label: Text(
                  quieto
                      ? 'Repintar (sin animación)'
                      : 'Repetir las animaciones',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Color
// ---------------------------------------------------------------------------

class _BloqueColor extends StatelessWidget {
  const _BloqueColor();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final List<_Muestra> muestras = <_Muestra>[
      _Muestra('fondo', p.fondo, 'Fondo de pantalla'),
      _Muestra('superficie', p.superficie, 'Tarjeta'),
      _Muestra('superficieElevada', p.superficieElevada, 'Hoja y modal'),
      _Muestra('lectura', p.lectura, 'Bloques de lección'),
      _Muestra('borde', p.borde, 'Separación sutil'),
      _Muestra('textoPrimario', p.textoPrimario, 'Texto principal'),
      _Muestra('textoSecundario', p.textoSecundario, 'Texto de apoyo'),
      _Muestra('arcano', p.arcano, 'Acción, foco y enlaces'),
      _Muestra('oro', p.oro, 'Oro, XP y recompensas'),
      _Muestra('brasa', p.brasa, 'Racha'),
      _Muestra('dominio', p.dominio, 'Dominio del saber'),
      _Muestra('exito', p.exito, 'Correcto'),
      _Muestra('advertencia', p.advertencia, '"Aún no", nunca castigo'),
      _Muestra('error', p.error, 'Fallo real del sistema'),
      _Muestra('info', p.info, 'Aviso neutro'),
    ];

    return _Seccion(
      titulo: 'Color',
      subtitulo:
          'Paleta semántica (`AteneaPalette`). Se lee con `context.paleta`; '
          'nunca se escribe un color literal en una pantalla.',
      hijos: <Widget>[
        _Rejilla(
          anchoMinimo: 168,
          hijos: <Widget>[
            for (final _Muestra m in muestras) _FichaColor(muestra: m),
          ],
        ),
        const SizedBox(height: Espacio.md),
        Text('Pares de contraste', style: context.textos.titleMedium),
        const SizedBox(height: Espacio.xs),
        _Rejilla(
          anchoMinimo: 200,
          hijos: <Widget>[
            _ParContraste(
              fondo: p.arcano,
              texto: p.sobreArcano,
              etiqueta: 'sobreArcano · botón primario',
            ),
            _ParContraste(
              fondo: p.oro,
              texto: p.sobreOro,
              etiqueta: 'sobreOro · recompensa',
            ),
          ],
        ),
      ],
    );
  }
}

class _Muestra {
  const _Muestra(this.nombre, this.color, this.uso);

  final String nombre;
  final Color color;
  final String uso;
}

class _FichaColor extends StatelessWidget {
  const _FichaColor({required this.muestra});

  final _Muestra muestra;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return Semantics(
      label: '${muestra.nombre}. ${muestra.uso}. ${_hex(muestra.color)}',
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Container(
              height: Medida.areaTactilMin,
              decoration: BoxDecoration(
                color: muestra.color,
                borderRadius: Redondeo.rChip,
                border: Border.all(color: p.borde),
              ),
            ),
            const SizedBox(height: Espacio.xxs + 2),
            Text(muestra.nombre, style: context.textos.titleMedium),
            Text(
              muestra.uso,
              style: context.textos.bodySmall?.copyWith(
                color: p.textoSecundario,
              ),
            ),
            Text(_hex(muestra.color), style: Cifras.pequena(context)),
          ],
        ),
      ),
    );
  }
}

class _ParContraste extends StatelessWidget {
  const _ParContraste({
    required this.fondo,
    required this.texto,
    required this.etiqueta,
  });

  final Color fondo;
  final Color texto;
  final String etiqueta;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Espacio.sm),
      decoration: BoxDecoration(
        color: fondo,
        borderRadius: Redondeo.rBoton,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            'Aa 1234',
            style: Cifras.media(context).copyWith(color: texto),
          ),
          Text(
            etiqueta,
            style: context.textos.bodySmall?.copyWith(color: texto),
          ),
        ],
      ),
    );
  }
}

String _hex(Color color) {
  final String v =
      color.toARGB32().toRadixString(16).padLeft(8, '0').toUpperCase();
  return '#${v.substring(2)}';
}

// ---------------------------------------------------------------------------
// Rareza
// ---------------------------------------------------------------------------

class _BloqueRareza extends StatelessWidget {
  const _BloqueRareza();

  @override
  Widget build(BuildContext context) {
    return _Seccion(
      titulo: 'Rareza',
      subtitulo:
          'Seis niveles con color, brillo y —siempre— etiqueta textual: el '
          'color jamás es el único portador de significado.',
      hijos: <Widget>[
        Wrap(
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            for (final Rareza r in Rareza.values) ChipRareza(rareza: r),
          ],
        ),
        const SizedBox(height: Espacio.md),
        _Rejilla(
          anchoMinimo: 150,
          hijos: <Widget>[
            for (final Rareza r in Rareza.values)
              TarjetaAtenea(
                colorBorde: r.color,
                brillo: reducirMovimiento(context) ? 0 : r.brillo,
                padding: const EdgeInsets.all(Espacio.sm),
                hijo: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Icon(
                      Icons.shield_moon_rounded,
                      color: r.color,
                      size: Espacio.xl,
                    ),
                    const SizedBox(height: Espacio.xs),
                    Text(r.etiqueta, style: context.textos.titleMedium),
                    Text(
                      'brillo ${r.brillo.round()} dp',
                      style: Cifras.pequena(context),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Tipografía
// ---------------------------------------------------------------------------

class _BloqueTipografia extends StatelessWidget {
  const _BloqueTipografia();

  @override
  Widget build(BuildContext context) {
    final TextTheme t = context.textos;
    final List<(String, String, TextStyle?)> escala =
        <(String, String, TextStyle?)>[
      ('displayLarge', 'Cinzel · ${Tipo.heroe.round()} dp', t.displayLarge),
      ('displayMedium', 'Cinzel · ${Tipo.display.round()} dp', t.displayMedium),
      ('displaySmall', 'Cinzel · ${Tipo.titulo.round()} dp', t.displaySmall),
      (
        'headlineMedium',
        'Nunito Sans · ${Tipo.titulo.round()} dp',
        t.headlineMedium,
      ),
      (
        'headlineSmall',
        'Nunito Sans · ${Tipo.subtitulo.round()} dp',
        t.headlineSmall,
      ),
      ('titleLarge', 'Nunito Sans · ${Tipo.subtitulo.round()} dp', t.titleLarge),
      ('titleMedium', 'Nunito Sans · ${Tipo.cuerpo.round()} dp', t.titleMedium),
      ('bodyLarge', 'Cuerpo · ${Tipo.cuerpo.round()} dp', t.bodyLarge),
      ('bodyMedium', 'Apoyo · ${Tipo.secundario.round()} dp', t.bodyMedium),
      ('bodySmall', 'Leyenda · ${Tipo.leyenda.round()} dp', t.bodySmall),
      ('labelLarge', 'Botón · ${Tipo.cuerpo.round()} dp', t.labelLarge),
    ];

    return _Seccion(
      titulo: 'Tipografía',
      subtitulo:
          'Cinzel solo en display y celebraciones, de 20 dp hacia arriba. '
          'Nunito Sans para toda la interfaz, con interlineado 1,5 en cuerpo.',
      hijos: <Widget>[
        for (final (String nombre, String detalle, TextStyle? estilo) in escala)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('$nombre · $detalle', style: Cifras.pequena(context)),
                Text('El saber es luz 1234', style: estilo),
              ],
            ),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Cifras
// ---------------------------------------------------------------------------

class _BloqueCifras extends StatelessWidget {
  const _BloqueCifras({required this.avance});

  final double avance;

  @override
  Widget build(BuildContext context) {
    final int xp = (avance * 1480).round();
    return _Seccion(
      titulo: 'Cifras',
      subtitulo:
          'Numerales tabulares: al animarse, los dígitos no cambian de ancho. '
          'Toda cifra del Reino llega del servidor; la app nunca la calcula.',
      hijos: <Widget>[
        Wrap(
          spacing: Espacio.lg,
          runSpacing: Espacio.md,
          crossAxisAlignment: WrapCrossAlignment.end,
          children: <Widget>[
            _EjemploCifra(
              nombre: 'Cifras.heroe',
              hijo: CifraAnimada(valor: xp, estilo: Cifras.heroe(context)),
            ),
            _EjemploCifra(
              nombre: 'Cifras.grande',
              hijo: CifraAnimada(valor: xp, estilo: Cifras.grande(context)),
            ),
            _EjemploCifra(
              nombre: 'Cifras.media',
              hijo: Text('1 111 · 8 888', style: Cifras.media(context)),
            ),
            _EjemploCifra(
              nombre: 'Cifras.pequena',
              hijo: Text('1 111 · 8 888', style: Cifras.pequena(context)),
            ),
          ],
        ),
      ],
    );
  }
}

class _EjemploCifra extends StatelessWidget {
  const _EjemploCifra({required this.nombre, required this.hijo});

  final String nombre;
  final Widget hijo;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(nombre, style: context.textos.bodySmall),
        hijo,
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Espacio, redondeo, movimiento y medida
// ---------------------------------------------------------------------------

class _BloqueEspacio extends StatelessWidget {
  const _BloqueEspacio();

  @override
  Widget build(BuildContext context) {
    const List<(String, double)> escala = <(String, double)>[
      ('xxs', Espacio.xxs),
      ('xs', Espacio.xs),
      ('sm', Espacio.sm),
      ('md', Espacio.md),
      ('lg', Espacio.lg),
      ('xl', Espacio.xl),
      ('xxl', Espacio.xxl),
    ];
    final AteneaPalette p = context.paleta;

    return _Seccion(
      titulo: 'Espacio',
      subtitulo: 'Toda separación de la interfaz sale de esta escala.',
      hijos: <Widget>[
        for (final (String nombre, double valor) in escala)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.xs),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    'Espacio.$nombre',
                    style: context.textos.bodyMedium,
                  ),
                ),
                const SizedBox(width: Espacio.xs),
                Text('${valor.round()} dp', style: Cifras.pequena(context)),
                const SizedBox(width: Espacio.xs),
                // La barra mide exactamente el valor del token.
                Container(
                  width: valor,
                  height: Espacio.sm,
                  decoration: BoxDecoration(
                    color: p.arcano,
                    borderRadius: Redondeo.rChip,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _BloqueRedondeo extends StatelessWidget {
  const _BloqueRedondeo();

  @override
  Widget build(BuildContext context) {
    const List<(String, double)> radios = <(String, double)>[
      ('chip', Redondeo.chip),
      ('boton', Redondeo.boton),
      ('tarjeta', Redondeo.tarjeta),
      ('hoja', Redondeo.hoja),
      ('pildora', Redondeo.pildora),
    ];
    final AteneaPalette p = context.paleta;

    return _Seccion(
      titulo: 'Redondeo',
      subtitulo: 'Cinco radios: del chip a la hoja inferior.',
      hijos: <Widget>[
        Wrap(
          spacing: Espacio.sm,
          runSpacing: Espacio.sm,
          children: <Widget>[
            for (final (String nombre, double radio) in radios)
              Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Container(
                    width: Espacio.xxl + Espacio.md,
                    height: Espacio.xxl,
                    decoration: BoxDecoration(
                      color: p.superficieElevada,
                      border: Border.all(color: p.arcano),
                      borderRadius: BorderRadius.circular(radio),
                    ),
                  ),
                  const SizedBox(height: Espacio.xxs),
                  Text(nombre, style: context.textos.bodySmall),
                  Text('${radio.round()} dp', style: Cifras.pequena(context)),
                ],
              ),
          ],
        ),
      ],
    );
  }
}

class _BloqueMovimiento extends StatefulWidget {
  const _BloqueMovimiento({required this.quieto});

  final bool quieto;

  @override
  State<_BloqueMovimiento> createState() => _BloqueMovimientoState();
}

class _BloqueMovimientoState extends State<_BloqueMovimiento> {
  bool _alFinal = false;

  @override
  Widget build(BuildContext context) {
    const List<(String, Duration)> duraciones = <(String, Duration)>[
      ('micro', Movimiento.micro),
      ('corta', Movimiento.corta),
      ('transicion', Movimiento.transicion),
      ('celebracion', Movimiento.celebracion),
      ('celebracionLarga', Movimiento.celebracionLarga),
    ];
    final AteneaPalette p = context.paleta;

    return _Seccion(
      titulo: 'Movimiento',
      subtitulo:
          'Ninguna celebración retiene al usuario más de 2,4 s. Con movimiento '
          'reducido todas estas duraciones valen cero y la versión estática '
          'toma el relevo.',
      hijos: <Widget>[
        for (final (String nombre, Duration d) in duraciones)
          Padding(
            padding: const EdgeInsets.only(bottom: Espacio.sm),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(nombre, style: context.textos.bodyMedium),
                    ),
                    const SizedBox(width: Espacio.xs),
                    Text(
                      '${d.inMilliseconds} ms',
                      style: Cifras.pequena(context),
                    ),
                  ],
                ),
                const SizedBox(height: Espacio.xxs),
                ClipRRect(
                  borderRadius: Redondeo.rChip,
                  child: Container(
                    height: Espacio.sm,
                    color: p.borde,
                    child: AnimatedFractionallySizedBox(
                      duration: widget.quieto ? Duration.zero : d,
                      curve: Movimiento.estandar,
                      alignment: Alignment.centerLeft,
                      widthFactor: _alFinal ? 1 : 0.06,
                      child: ColoredBox(color: p.oro),
                    ),
                  ),
                ),
              ],
            ),
          ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => setState(() => _alFinal = !_alFinal),
            icon: const Icon(Icons.play_arrow_rounded),
            label: Text(_alFinal ? 'Volver al inicio' : 'Lanzar'),
          ),
        ),
        Text(
          'Curvas: estandar (easeOutCubic) para lo cotidiano, entrada '
          '(easeOutBack) solo para lo que celebra.',
          style: context.textos.bodySmall?.copyWith(color: p.textoSecundario),
        ),
      ],
    );
  }
}

class _BloqueMedida extends StatelessWidget {
  const _BloqueMedida();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return _Seccion(
      titulo: 'Medida',
      subtitulo: 'Ancho de lectura y área táctil mínima.',
      hijos: <Widget>[
        FilaDato(
          etiqueta: 'Medida.lecturaMax',
          valor: '${Medida.lecturaMax.round()} dp',
          icono: Icons.chrome_reader_mode_rounded,
        ),
        FilaDato(
          etiqueta: 'Medida.areaTactilMin',
          valor: '${Medida.areaTactilMin.round()} dp',
          icono: Icons.touch_app_rounded,
        ),
        const SizedBox(height: Espacio.xs),
        Row(
          children: <Widget>[
            Container(
              width: Medida.areaTactilMin,
              height: Medida.areaTactilMin,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                borderRadius: Redondeo.rBoton,
                border: Border.all(color: p.exito),
              ),
              child: Icon(Icons.check_rounded, color: p.exito),
            ),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Text(
                'Todo lo que se toca ocupa al menos este cuadrado, aunque su '
                'dibujo sea más pequeño.',
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Componentes
// ---------------------------------------------------------------------------

class _BloqueMedallones extends StatelessWidget {
  const _BloqueMedallones();

  @override
  Widget build(BuildContext context) {
    const Map<Medallon, String> valores = <Medallon, String>{
      Medallon.xp: '1 480',
      Medallon.oro: '320',
      Medallon.racha: '7 días',
      Medallon.dominio: '62 %',
      Medallon.tiempo: '45 min',
      Medallon.nivel: '4',
    };

    return _Seccion(
      titulo: 'Medallones',
      subtitulo:
          'Las seis cifras del juego. Cada una lleva icono, color y etiqueta, '
          'y anuncia su valor al lector de pantalla.',
      hijos: <Widget>[
        _Rejilla(
          anchoMinimo: 120,
          hijos: <Widget>[
            for (final MapEntry<Medallon, String> e in valores.entries)
              FichaMedallon(tipo: e.key, valor: e.value),
          ],
        ),
        const SizedBox(height: Espacio.md),
        Text('Versión compacta', style: context.textos.titleMedium),
        const SizedBox(height: Espacio.xs),
        Wrap(
          spacing: Espacio.md,
          runSpacing: Espacio.xs,
          children: <Widget>[
            for (final MapEntry<Medallon, String> e in valores.entries)
              FichaMedallon(tipo: e.key, valor: e.value, compacto: true),
          ],
        ),
      ],
    );
  }
}

class _BloqueBarras extends StatelessWidget {
  const _BloqueBarras({required this.avance});

  final double avance;

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return _Seccion(
      titulo: 'Progreso',
      subtitulo:
          'La barra siempre dice qué mide y cuánto falta; nunca se deja sola '
          'con su color.',
      hijos: <Widget>[
        BarraProgreso(
          valor: avance,
          etiqueta: 'XP al siguiente nivel',
          textoDerecha: '${(avance * 100).round()} %',
        ),
        const SizedBox(height: Espacio.md),
        BarraProgreso(
          valor: avance,
          etiqueta: 'Dominio de Álgebra',
          textoDerecha: '${(avance * 100).round()} %',
          color: p.dominio,
        ),
        const SizedBox(height: Espacio.md),
        BarraProgreso(
          valor: avance,
          etiqueta: 'Objetivo diario',
          textoDerecha: '${(avance * 20).round()} de 20 min',
          color: p.oro,
          alto: Espacio.md,
        ),
      ],
    );
  }
}

class _BloqueTarjetas extends StatelessWidget {
  const _BloqueTarjetas();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    final bool quieto = reducirMovimiento(context);
    return _Seccion(
      titulo: 'Tarjetas',
      subtitulo:
          'Superficie, borde sutil y radio de 16 dp. El resplandor se reserva '
          'a recompensas y rarezas.',
      hijos: <Widget>[
        const TarjetaAtenea(
          hijo: Text(
            'TarjetaAtenea · plana. La unidad básica de contenido del Reino.',
          ),
        ),
        const SizedBox(height: Espacio.sm),
        const TarjetaAtenea(
          elevada: true,
          hijo: Text(
            'TarjetaAtenea · elevada. Hojas, modales y bloques destacados.',
          ),
        ),
        const SizedBox(height: Espacio.sm),
        TarjetaAtenea(
          colorBorde: p.oro,
          brillo: quieto ? 0 : 12,
          hijo: Row(
            children: <Widget>[
              Icon(Icons.emoji_events_rounded, color: p.oro),
              const SizedBox(width: Espacio.sm),
              const Expanded(
                child: Text('TarjetaAtenea · con borde de acento y brillo.'),
              ),
            ],
          ),
        ),
        const SizedBox(height: Espacio.sm),
        TarjetaAtenea(
          alTocar: () {},
          semantica: 'Tarjeta de ejemplo, tocable',
          hijo: Row(
            children: <Widget>[
              const Expanded(
                child: Text('TarjetaAtenea · tocable, con respuesta al toque.'),
              ),
              Icon(Icons.chevron_right_rounded, color: p.textoSecundario),
            ],
          ),
        ),
      ],
    );
  }
}

class _BloqueBotones extends StatelessWidget {
  const _BloqueBotones();

  @override
  Widget build(BuildContext context) {
    return _Seccion(
      titulo: 'Botones',
      subtitulo:
          'Una sola acción primaria por pantalla. El texto dice lo que va a '
          'ocurrir, nunca "Aceptar".',
      hijos: <Widget>[
        BotonPrimario(texto: 'Continuar tu aventura', alTocar: () {}),
        const SizedBox(height: Espacio.sm),
        BotonPrimario(
          texto: 'Empezar la lección',
          subtitulo: '8 min · +40 XP',
          icono: Icons.play_arrow_rounded,
          alTocar: () {},
        ),
        const SizedBox(height: Espacio.sm),
        const BotonPrimario(
          texto: 'Forjando tu ruta',
          alTocar: null,
          cargando: true,
        ),
        const SizedBox(height: Espacio.sm),
        const BotonPrimario(texto: 'Deshabilitado', alTocar: null),
        const SizedBox(height: Espacio.md),
        Wrap(
          spacing: Espacio.sm,
          runSpacing: Espacio.xs,
          children: <Widget>[
            OutlinedButton(onPressed: () {}, child: const Text('Secundario')),
            TextButton(onPressed: () {}, child: const Text('Terciario')),
            IconButton(
              tooltip: 'Icono',
              onPressed: () {},
              icon: const Icon(Icons.more_horiz_rounded),
            ),
          ],
        ),
      ],
    );
  }
}

class _BloquePiezas extends StatelessWidget {
  const _BloquePiezas();

  @override
  Widget build(BuildContext context) {
    final AteneaPalette p = context.paleta;
    return _Seccion(
      titulo: 'Piezas sueltas',
      subtitulo: 'Píldoras, filas de dato, encabezados y ornamentos.',
      hijos: <Widget>[
        Wrap(
          spacing: Espacio.xs,
          runSpacing: Espacio.xs,
          children: <Widget>[
            const Pildora(texto: 'Territorio: Números'),
            Pildora(
              texto: 'Misión diaria',
              icono: Icons.flag_rounded,
              color: p.arcano,
            ),
            Pildora(
              texto: 'Repaso',
              icono: Icons.refresh_rounded,
              color: p.dominio,
            ),
            Pildora(
              texto: 'Material escaso',
              icono: Icons.info_outline_rounded,
              color: p.advertencia,
            ),
          ],
        ),
        const SizedBox(height: Espacio.md),
        const TarjetaAtenea(
          hijo: Column(
            children: <Widget>[
              FilaDato(
                etiqueta: 'Preguntas',
                valor: '10',
                icono: Icons.help_outline_rounded,
              ),
              FilaDato(
                etiqueta: 'Umbral para superarlo',
                valor: '70 %',
                icono: Icons.flag_rounded,
              ),
              FilaDato(
                etiqueta: 'Mejor marca',
                valor: '80 %',
                icono: Icons.military_tech_rounded,
              ),
            ],
          ),
        ),
        EncabezadoSeccion(
          titulo: 'Encabezado de sección',
          subtitulo: 'Con subtítulo y acción a la derecha',
          textoAccion: 'Ver todo',
          alTocarAccion: () {},
        ),
        Row(
          children: <Widget>[
            OrnamentoEsquina(color: p.oro),
            const SizedBox(width: Espacio.sm),
            Expanded(
              child: Text(
                'OrnamentoEsquina: filigrana reservada a celebraciones y a '
                'tarjetas de ítem, nunca a la interfaz general.',
                style: context.textos.bodyMedium?.copyWith(
                  color: p.textoSecundario,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _BloqueEstados extends StatelessWidget {
  const _BloqueEstados();

  @override
  Widget build(BuildContext context) {
    return _Seccion(
      titulo: 'Estados',
      subtitulo:
          'Carga, vacío y error. Ninguno culpa al usuario y todos ofrecen una '
          'salida.',
      hijos: <Widget>[
        const TarjetaAtenea(
          padding: EdgeInsets.all(Espacio.lg),
          hijo: EstadoCarga(mensaje: 'Forjando tu leyenda…'),
        ),
        const SizedBox(height: Espacio.sm),
        TarjetaAtenea(
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text('Esqueleto de lista', style: context.textos.titleMedium),
              const SizedBox(height: Espacio.sm),
              const Esqueleto(alto: Espacio.lg),
              const SizedBox(height: Espacio.xs),
              const Esqueleto(alto: Espacio.md, ancho: 220),
              const SizedBox(height: Espacio.xs),
              const Esqueleto(alto: Espacio.md, ancho: 140),
            ],
          ),
        ),
        const SizedBox(height: Espacio.sm),
        TarjetaAtenea(
          hijo: EstadoVacio(
            icono: Icons.map_rounded,
            titulo: 'Tu Reino aún está en bruma',
            mensaje: 'Crea tu primera Ruta y el mapa empezará a iluminarse.',
            textoAccion: 'Crear una ruta',
            alTocarAccion: () {},
          ),
        ),
        const SizedBox(height: Espacio.sm),
        TarjetaAtenea(
          hijo: EstadoError(
            mensaje: 'No pudimos alcanzar el Reino. Revisa tu conexión y lo '
                'intentamos de nuevo.',
            alReintentar: () {},
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Andamiaje de la galería
// ---------------------------------------------------------------------------

/// Sección de la galería: encabezado más contenido en una tarjeta.
class _Seccion extends StatelessWidget {
  const _Seccion({
    required this.titulo,
    required this.subtitulo,
    required this.hijos,
  });

  final String titulo;
  final String subtitulo;
  final List<Widget> hijos;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        EncabezadoSeccion(titulo: titulo, subtitulo: subtitulo),
        TarjetaAtenea(
          hijo: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: hijos,
          ),
        ),
      ],
    );
  }
}

/// Rejilla fluida: tantas columnas como quepan con [anchoMinimo].
///
/// Se resuelve con `Wrap` y `LayoutBuilder` en vez de `GridView` para que la
/// altura la fije el contenido y nada desborde al 200 % de escala de texto.
class _Rejilla extends StatelessWidget {
  const _Rejilla({required this.anchoMinimo, required this.hijos});

  final double anchoMinimo;
  final List<Widget> hijos;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints limites) {
        final double disponible = limites.maxWidth;
        final int columnas = disponible <= anchoMinimo
            ? 1
            : (disponible / anchoMinimo).floor().clamp(1, 6);
        final double ancho =
            (disponible - Espacio.sm * (columnas - 1)) / columnas;
        return Wrap(
          spacing: Espacio.sm,
          runSpacing: Espacio.sm,
          children: <Widget>[
            for (final Widget hijo in hijos)
              SizedBox(width: ancho > 0 ? ancho : disponible, child: hijo),
          ],
        );
      },
    );
  }
}
